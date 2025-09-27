# routes/api_routes.py
import time
from datetime import datetime
from flask import Blueprint, request, jsonify
from services.openai_service import (
    analyze_with_openai,
    load_image_from_url,
    OPENAI_AVAILABLE,
    openai_error_message,
    init_openai,
    openai_last_check
)
from database.operations import get_user_by_telegram_id, redeem_registration_key

api_bp = Blueprint('api_bp', __name__)

# Keep in-memory sessions (for now). Keyed by telegram_user_id
analysis_sessions = {}

@api_bp.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

@api_bp.route('/redeem-key', methods=['POST'])
def redeem_key_route():
    """
    Endpoint to redeem a registration key.
    Expected JSON: { "telegram_user_id": 123456789, "key": "ABC123" }
    Returns success or error JSON with expiry_date on success.
    """
    data = request.get_json() or {}
    telegram_user_id = data.get('telegram_user_id')
    key_value = data.get('key')

    if not telegram_user_id or not key_value:
        return jsonify({"success": False, "error": "telegram_user_id and key are required"}), 400

    result = redeem_registration_key(key_value, telegram_user_id)
    if not result.get('success'):
        return jsonify(result), 400

    return jsonify(result), 200

@api_bp.route('/analyze', methods=['POST'])
def analyze():
    """
    Main analyze endpoint.
    This endpoint expects the request to include 'telegram_user_id' in the JSON payload
    so we can verify registration before proceeding. If telegram_user_id isn't provided,
    the endpoint will respond with an error telling the bot to request it.
    """
    try:
        if not request.is_json:
            return jsonify({
                "success": False,
                "message": "نوع المحتوى غير مدعوم",
                "analysis": "يجب أن يكون الطلب بتنسيق JSON"
            }), 415

        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "لم يتم إرسال بيانات",
                "analysis": "لم يتم إرسال بيانات للتحليل"
            }), 400

        telegram_user_id = data.get('telegram_user_id')
        if not telegram_user_id:
            # instruct the bot to ask for the user's telegram id or to send it automatically
            return jsonify({
                "success": False,
                "code": "missing_telegram_id",
                "message": "Please include your telegram_user_id. The bot should send it automatically or ask the user for their ID or key."
            }), 400

        # Ensure telegram_user_id is numeric
        try:
            telegram_user_id = int(telegram_user_id)
        except Exception:
            return jsonify({"success": False, "message": "Invalid telegram_user_id"}), 400

        # Check user registration status
        user = get_user_by_telegram_id(telegram_user_id)
        if not user:
            # Not registered yet -> instruct bot to ask for registration key
            return jsonify({
                "success": False,
                "code": "not_registered",
                "message": "Your account is not registered. Please send your registration key using the /redeem-key flow."
            }), 403

        # Check expiry
        expiry = user.get('expiry_date')
        if expiry and isinstance(expiry, str):
            # If stored as ISO string convert to datetime
            try:
                expiry = datetime.fromisoformat(expiry)
            except Exception:
                expiry = expiry  # leave as-is; comparison may fail below

        if expiry and datetime.utcnow() > expiry:
            # expired
            return jsonify({
                "success": False,
                "code": "expired",
                "message": "Your subscription has expired. Please renew or contact admin."
            }), 403

        # Passed registration checks; proceed with existing analysis logic
        user_id = data.get('user_id', telegram_user_id)  # keep fallback
        action_type = data.get('action_type', 'chart_analysis')  # chart_analysis, add_timeframe, user_analysis
        image_url = data.get('image_url')
        user_analysis_text = data.get('user_analysis')
        timeframe = data.get('timeframe', 'M15')

        # Initialize session storage for this user
        if telegram_user_id not in analysis_sessions:
            analysis_sessions[telegram_user_id] = {
                'user_id': telegram_user_id,
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'created_at': datetime.now(),
                'status': 'ready',
                'conversation_history': []
            }

        session_data = analysis_sessions[telegram_user_id]

        # load image if present
        image_str = None
        image_format = None
        if image_url:
            image_str, image_format = load_image_from_url(image_url)

        if not OPENAI_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": openai_error_message
            }), 503

        # handle action types (chart_analysis, add_timeframe, user_analysis, new_analysis)
        if action_type == 'chart_analysis':
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "تعذر تحميل الصورة المطلوبة"
                }), 400

            analysis = analyze_with_openai(image_str, image_format, timeframe)
            session_data['first_analysis'] = analysis
            session_data['first_timeframe'] = timeframe
            session_data['status'] = 'first_analysis_done'

            session_data['conversation_history'].append({
                'type': 'analysis',
                'timeframe': timeframe,
                'content': analysis,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": f"✅ تم تحليل {timeframe} بنجاح",
                "analysis": analysis,
                "user_id": telegram_user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "add_timeframe", "label": "➕ إضافة إطار زمني آخر"},
                    {"action": "user_analysis", "label": "📝 إضافة تحليلي الشخصي"}
                ]
            }), 200

        elif action_type == 'add_timeframe':
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "تعذر تحميل الصورة المطلوبة"
                }), 400

            if session_data['status'] != 'first_analysis_done':
                return jsonify({
                    "success": False,
                    "message": "خطأ في التسلسل",
                    "analysis": "يجب تحليل الإطار الأول قبل إضافة الثاني"
                }), 400

            # determine opposite timeframe
            if session_data['first_timeframe'] == 'M15':
                new_timeframe = 'H4'
            else:
                new_timeframe = 'M15'

            analysis = analyze_with_openai(image_str, image_format, new_timeframe, session_data['first_analysis'])
            session_data['second_analysis'] = analysis
            session_data['second_timeframe'] = new_timeframe
            session_data['status'] = 'both_analyses_done'

            # combined final analysis (aggregate)
            final_analysis = analyze_with_openai(
                None, None, "H4",
                f"{session_data['first_timeframe']}: {session_data['first_analysis']}",
                None, "chart_analysis"
            )

            session_data['conversation_history'].append({
                'type': 'analysis',
                'timeframe': new_timeframe,
                'content': analysis,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "user_id": telegram_user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "user_analysis", "label": "📝 إضافة تحليلي الشخصي للحصول على تقييم"}
                ]
            }), 200

        elif action_type == 'user_analysis':
            if not user_analysis_text:
                return jsonify({
                    "success": False,
                    "message": "تحليل نصي مطلوب",
                    "analysis": "يرجى تقديم تحليلك النصي"
                }), 400

            feedback = analyze_with_openai(
                image_str, image_format if image_str else None,
                None, None, user_analysis_text, "user_analysis_feedback"
            )

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'user_analysis_reviewed'

            session_data['conversation_history'].append({
                'type': 'user_analysis',
                'content': user_analysis_text,
                'feedback': feedback,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "user_id": telegram_user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "new_analysis", "label": "🔄 بدء تحليل جديد"}
                ]
            }), 200

        elif action_type == 'new_analysis':
            # start a fresh analysis session but keep conversation history
            analysis_sessions[telegram_user_id] = {
                'user_id': telegram_user_id,
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'created_at': datetime.now(),
                'status': 'ready',
                'conversation_history': session_data.get('conversation_history', [])
            }

            return jsonify({
                "success": True,
                "message": "🔄 تم بدء جلسة تحليل جديدة",
                "analysis": "يمكنك الآن إرسال صورة الرسم البياني للتحليل",
                "user_id": telegram_user_id,
                "status": 'ready',
                "next_actions": [
                    {"action": "chart_analysis", "label": "📊 تحليل رسم بياني", "requires_image": True}
                ]
            }), 200

        else:
            return jsonify({
                "success": False,
                "message": "نوع إجراء غير معروف",
                "analysis": f"نوع الإجراء {action_type} غير مدعوم"
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"خطأ أثناء المعالجة: {str(e)}",
            "analysis": f"فشل في التحليل: {str(e)}"
        }), 400

@api_bp.route('/sendpulse-analyze', methods=['POST'])
def sendpulse_analyze():
    data = request.get_json()
    if data:
        data['action_type'] = 'chart_analysis'
        if 'timeframe' not in data:
            data['timeframe'] = 'M15'
    return analyze()

@api_bp.route('/multi-timeframe-analyze', methods=['POST'])
def multi_timeframe_analyze():
    return sendpulse_analyze()

@api_bp.route('/user-analysis', methods=['POST'])
def user_analysis_route():
    data = request.get_json()
    if data:
        data['action_type'] = 'user_analysis'
    return analyze()

@api_bp.route('/status')
def status_route():
    # refresh OpenAI status periodically
    if time.time() - openai_last_check > 300:
        try:
            init_openai()
        except Exception:
            pass

    return jsonify({
        "server": "running",
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message,
        "active_sessions": len(analysis_sessions),
        "timestamp": time.time()
    })

@api_bp.route('/session-info/<int:telegram_user_id>')
def session_info(telegram_user_id):
    if telegram_user_id in analysis_sessions:
        session_data = analysis_sessions[telegram_user_id].copy()
        if 'conversation_history' in session_data:
            session_data['conversation_count'] = len(session_data['conversation_history'])
            del session_data['conversation_history']
        return jsonify({"success": True, "session": session_data})
    else:
        return jsonify({"success": False, "message": "الجلسة غير موجودة"})

@api_bp.route('/clear-sessions')
def clear_sessions():
    global analysis_sessions
    count = len(analysis_sessions)
    analysis_sessions = {}
    return jsonify({
        "message": f"تم مسح {count} جلسة",
        "status": "sessions_cleared"
    })

