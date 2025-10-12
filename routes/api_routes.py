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
        # LOG INCOMING REQUEST
        print(f"🚨 ANALYZE ENDPOINT: Received request at {datetime.now()}")
        print(f"🚨 ANALYZE ENDPOINT: Headers: {dict(request.headers)}")
        print(f"🚨 ANALYZE ENDPOINT: Content-Type: {request.content_type}")

        if not request.is_json:
            error_response = {
                "success": False,
                "message": "نوع المحتوى غير مدعوم"
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Not JSON: {error_response}")
            return jsonify(error_response), 415

        data = request.get_json()
        print(f"🚨 ANALYZE ENDPOINT: 📥 Received JSON data: {data}")

        if not data:
            error_response = {
                "success": False,
                "message": "لم يتم إرسال بيانات"
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - No data: {error_response}")
            return jsonify(error_response), 400

        telegram_user_id = data.get('telegram_user_id')
        action_type = data.get('action_type', 'first_analysis')
        image_url = data.get('image_url')

        print(f"🚨 ANALYZE ENDPOINT: 👤 Telegram ID: {telegram_user_id}")
        print(f"🚨 ANALYZE ENDPOINT: 🎯 Action Type: {action_type}")
        print(f"🚨 ANALYZE ENDPOINT: 🖼️ Image URL: {image_url}")

        if not telegram_user_id:
            error_response = {
                "success": False,
                "code": "missing_telegram_id",
                "message": "Please include your telegram_user_id"
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Missing telegram ID: {error_response}")
            return jsonify(error_response), 400

        # Ensure telegram_user_id is numeric
        try:
            telegram_user_id = int(telegram_user_id)
        except Exception:
            error_response = {"success": False, "message": "Invalid telegram_user_id"}
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Invalid telegram ID: {error_response}")
            return jsonify(error_response), 400

        # Check user registration status
        user = get_user_by_telegram_id(telegram_user_id)
        if not user:
            error_response = {
                "success": False,
                "code": "not_registered",
                "message": "Your account is not registered. Please send your registration key using /redeem-key"
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - User not registered: {error_response}")
            return jsonify(error_response), 403

        # Check expiry
        expiry = user.get('expiry_date')
        if expiry and isinstance(expiry, str):
            try:
                expiry = datetime.fromisoformat(expiry)
            except Exception:
                expiry = expiry

        if expiry and datetime.utcnow() > expiry:
            error_response = {
                "success": False,
                "code": "expired",
                "message": "Your subscription has expired. Please renew or contact admin."
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Subscription expired: {error_response}")
            return jsonify(error_response), 403

        # Check OpenAI availability using current_app.config
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'Unknown error')
            error_response = {
                "success": False,
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": openai_error
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - OpenAI unavailable: {error_response}")
            return jsonify(error_response), 503

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
        user_analysis_text = data.get('user_analysis')
        timeframe = data.get('timeframe', 'M15')

        print(f"🚨 ANALYZE ENDPOINT: 💾 Session data: {session_data}")

        # Load image if provided
        image_str, image_format = None, None
        if image_url:
            print(f"🚨 ANALYZE ENDPOINT: 📥 Loading image from URL: {image_url}")
            image_str, image_format = load_image_from_url(image_url)
            print(f"🚨 ANALYZE ENDPOINT: 🖼️ Image loaded - String: {bool(image_str)}, Format: {image_format}")

        # Handle different action types
        if action_type == 'first_analysis':
            if not image_str:
                error_response = {
                    "success": False,
                    "message": "صورة غير صالحة"
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Invalid image: {error_response}")
                return jsonify(error_response), 400

            print(f"🚨 ANALYZE ENDPOINT: 🧠 Starting first analysis with timeframe: {timeframe}")
            analysis = analyze_with_openai(image_str, image_format, timeframe, action_type='first_analysis')
            
            # Check if analysis returned a validation error (starts with ❌)
            if analysis.startswith('❌'):
                error_response = {
                    "success": False,
                    "message": analysis
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Timeframe validation failed: {analysis}")
                return jsonify(error_response), 400
            
            session_data['first_analysis'] = analysis
            session_data['first_timeframe'] = timeframe
            session_data['status'] = 'first_done'

            response_data = {
                "success": True,
                "message": f"✅ تم تحليل {timeframe} بنجاح",
                "analysis": analysis,
                "next_action": "second_analysis",
                "next_prompt": "الآن أرسل صورة الإطار الزمني الثاني (H4) لنفس العملة"
            }
            print(f"🚨 ANALYZE ENDPOINT: ✅ First analysis completed - Response: {response_data}")
            return jsonify(response_data), 200

        elif action_type == 'second_analysis':
            print(f"🚨 ANALYZE ENDPOINT: 🔄 Starting second analysis")

            if not image_str:
                error_response = {
                    "success": False,
                    "message": "صورة غير صالحة"
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Invalid image: {error_response}")
                return jsonify(error_response), 400

            if session_data['status'] != 'first_done':
                error_response = {
                    "success": False,
                    "message": "يجب تحليل الإطار الأول قبل الثاني"
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - First analysis not done: {error_response}")
                return jsonify(error_response), 400

            # Use H4 for second analysis
            second_timeframe = 'H4'
            print(f"🚨 ANALYZE ENDPOINT: 🧠 Starting second analysis with timeframe: {second_timeframe}")
            analysis = analyze_with_openai(image_str, image_format, second_timeframe, session_data['first_analysis'], action_type='second_analysis')
            
            # Check if analysis returned a validation error (starts with ❌)
            if analysis.startswith('❌'):
                error_response = {
                    "success": False,
                    "message": analysis
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Timeframe validation failed: {analysis}")
                return jsonify(error_response), 400
            
            session_data['second_analysis'] = analysis
            session_data['second_timeframe'] = second_timeframe
            session_data['status'] = 'both_done'

            print(f"🚨 ANALYZE ENDPOINT: 🧠 Generating final combined analysis")
            # Generate final combined analysis
            final_analysis = analyze_with_openai(
                None, None, "combined",
                f"{session_data['first_timeframe']}: {session_data['first_analysis']}",
                session_data['second_analysis'], "final_analysis"
            )

            response_data = {
                "success": True,
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "next_action": "user_analysis",
                "next_prompt": "هل تريد مشاركة تحليلك الشخصي للحصول على تقييم؟"
            }
            print(f"🚨 ANALYZE ENDPOINT: ✅ Second analysis completed - Response: {response_data}")
            return jsonify(response_data), 200

        elif action_type == 'user_analysis':
            print(f"🚨 ANALYZE ENDPOINT: 👤 Starting user analysis feedback")

            if not user_analysis_text:
                error_response = {
                    "success": False,
                    "message": "تحليل نصي مطلوب"
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - No user analysis: {error_response}")
                return jsonify(error_response), 400

            feedback = analyze_with_openai(
                None, None, None, None, user_analysis_text, "user_analysis_feedback"
            )

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'completed'

            response_data = {
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "next_action": "new_session",
                "next_prompt": "يمكنك بدء تحليل جديد"
            }
            print(f"🚨 ANALYZE ENDPOINT: ✅ User analysis completed - Response: {response_data}")
            return jsonify(response_data), 200

        elif action_type == 'new_session':
            print(f"🚨 ANALYZE ENDPOINT: 🔄 Starting new session")
            # Reset session but keep conversation history if needed
            analysis_sessions[telegram_user_id] = {
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'status': 'ready'
            }

            response_data = {
                "success": True,
                "message": "🔄 تم بدء جلسة تحليل جديدة",
                "next_action": "first_analysis",
                "next_prompt": "أرسل صورة الرسم البياني الأول للتحليل"
            }
            print(f"🚨 ANALYZE ENDPOINT: ✅ New session started - Response: {response_data}")
            return jsonify(response_data), 200

        else:
            error_response = {
                "success": False,
                "message": "نوع إجراء غير معروف"
            }
            print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - Unknown action type: {error_response}")
            return jsonify(error_response), 400

    except Exception as e:
        error_response = {
            "success": False,
            "message": f"خطأ أثناء المعالجة: {str(e)}"
        }
        print(f"🚨 ANALYZE ENDPOINT: ❌ Exception occurred: {str(e)}")
        print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error: {error_response}")
        return jsonify(error_response), 400

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
