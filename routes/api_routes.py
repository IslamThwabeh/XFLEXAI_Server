# routes/api_routes.py
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from services.openai_service import (
    analyze_with_openai,
    load_image_from_url
)
from database.operations import get_user_by_telegram_id, redeem_registration_key

api_bp = Blueprint('api_bp', __name__)
analysis_sessions = {}

@api_bp.route('/')
def home():
    openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
    openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'Unknown error')
    status = "✅" if openai_available else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if openai_available else openai_error}"

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
    SIMPLIFIED ANALYSIS ENDPOINT - handles all analysis types
    Action types: first_analysis, second_analysis, user_analysis, new_session
    """
    try:
        if not request.is_json:
            return jsonify({
                "success": False,
                "message": "نوع المحتوى غير مدعوم"
            }), 415

        data = request.get_json()
        if not data:
            return jsonify({
                "success": False, 
                "message": "لم يتم إرسال بيانات"
            }), 400

        telegram_user_id = data.get('telegram_user_id')
        if not telegram_user_id:
            return jsonify({
                "success": False,
                "code": "missing_telegram_id",
                "message": "Please include your telegram_user_id"
            }), 400

        # Ensure telegram_user_id is numeric
        try:
            telegram_user_id = int(telegram_user_id)
        except Exception:
            return jsonify({"success": False, "message": "Invalid telegram_user_id"}), 400

        # Check user registration status
        user = get_user_by_telegram_id(telegram_user_id)
        if not user:
            return jsonify({
                "success": False,
                "code": "not_registered",
                "message": "Your account is not registered. Please send your registration key using /redeem-key"
            }), 403

        # Check expiry
        expiry = user.get('expiry_date')
        if expiry and isinstance(expiry, str):
            try:
                expiry = datetime.fromisoformat(expiry)
            except Exception:
                expiry = expiry

        if expiry and datetime.utcnow() > expiry:
            return jsonify({
                "success": False,
                "code": "expired", 
                "message": "Your subscription has expired. Please renew or contact admin."
            }), 403

        # Check OpenAI availability using current_app.config
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'Unknown error')
            return jsonify({
                "success": False,
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": openai_error
            }), 503

        # Initialize or get session
        if telegram_user_id not in analysis_sessions:
            analysis_sessions[telegram_user_id] = {
                'first_analysis': None,
                'second_analysis': None, 
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'status': 'ready'
            }

        session_data = analysis_sessions[telegram_user_id]
        action_type = data.get('action_type', 'first_analysis')
        image_url = data.get('image_url')
        user_analysis_text = data.get('user_analysis')
        timeframe = data.get('timeframe', 'M15')

        # Load image if provided
        image_str, image_format = None, None
        if image_url:
            image_str, image_format = load_image_from_url(image_url)

        # Handle different action types
        if action_type == 'first_analysis':
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة"
                }), 400

            analysis = analyze_with_openai(image_str, image_format, timeframe)
            session_data['first_analysis'] = analysis
            session_data['first_timeframe'] = timeframe
            session_data['status'] = 'first_done'

            return jsonify({
                "success": True,
                "message": f"✅ تم تحليل {timeframe} بنجاح",
                "analysis": analysis,
                "next_action": "second_analysis",
                "next_prompt": "الآن أرسل صورة الإطار الزمني الثاني (H4) لنفس العملة"
            }), 200

        elif action_type == 'second_analysis':
            if not image_str:
                return jsonify({
                    "success": False, 
                    "message": "صورة غير صالحة"
                }), 400

            if session_data['status'] != 'first_done':
                return jsonify({
                    "success": False,
                    "message": "يجب تحليل الإطار الأول قبل الثاني"
                }), 400

            # Use H4 for second analysis
            second_timeframe = 'H4'
            analysis = analyze_with_openai(image_str, image_format, second_timeframe, session_data['first_analysis'])
            session_data['second_analysis'] = analysis
            session_data['second_timeframe'] = second_timeframe
            session_data['status'] = 'both_done'

            # Generate final combined analysis
            final_analysis = analyze_with_openai(
                None, None, "combined",
                f"{session_data['first_timeframe']}: {session_data['first_analysis']}",
                None, "final_analysis"
            )

            return jsonify({
                "success": True,
                "message": "✅ تم التحليل الشامل بنجاح",
                "next_action": "user_analysis", 
                "next_prompt": "هل تريد مشاركة تحليلك الشخصي للحصول على تقييم؟"
                "analysis": final_analysis,
            }), 200

        elif action_type == 'user_analysis':
            if not user_analysis_text:
                return jsonify({
                    "success": False,
                    "message": "تحليل نصي مطلوب"
                }), 400

            feedback = analyze_with_openai(
                None, None, None, None, user_analysis_text, "user_analysis_feedback"
            )

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'completed'

            return jsonify({
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "next_action": "new_session",
                "next_prompt": "يمكنك بدء تحليل جديد"
            }), 200

        elif action_type == 'new_session':
            # Reset session but keep conversation history if needed
            analysis_sessions[telegram_user_id] = {
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None, 
                'second_timeframe': None,
                'user_analysis': None,
                'status': 'ready'
            }

            return jsonify({
                "success": True,
                "message": "🔄 تم بدء جلسة تحليل جديدة",
                "next_action": "first_analysis",
                "next_prompt": "أرسل صورة الرسم البياني الأول للتحليل"
            }), 200

        else:
            return jsonify({
                "success": False,
                "message": "نوع إجراء غير معروف"
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"خطأ أثناء المعالجة: {str(e)}"
        }), 400

@api_bp.route('/status')
def status_route():
    openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
    return jsonify({
        "server": "running",
        "openai_available": openai_available,
        "active_sessions": len(analysis_sessions)
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
