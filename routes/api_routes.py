# routes/api_routes.py
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from services.openai_service import (
    analyze_with_openai,
    load_image_from_url,
    detect_timeframe_from_image,
    analyze_technical_chart,
    analyze_user_drawn_feedback_simple,
    detect_currency_from_image,
    validate_currency_consistency,
    shorten_analysis_text,
    detect_investing_frame,
    extract_investing_data,
    analyze_simple_chart_fallback
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
    ALL RESPONSES LIMITED TO 1024 CHARACTERS FOR SENDPULSE
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
                'first_currency': None,
                'second_currency': None,
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
                return jsonify(error_response), 200

            print(f"🚨 ANALYZE ENDPOINT: 🧠 Starting first analysis with timeframe: {timeframe}")
            
            # Detect currency from first image
            print(f"🪙 ANALYZE ENDPOINT: Detecting currency from first image...")
            first_currency, currency_error = detect_currency_from_image(image_str, image_format)
            print(f"🪙 ANALYZE ENDPOINT: First currency detected: {first_currency}")
            
            # Pass currency pair to analysis for proper stop loss rules
            analysis = analyze_with_openai(image_str, image_format, timeframe, action_type='first_analysis', currency_pair=first_currency)

            # Check if analysis returned a validation error (starts with ❌)
            if analysis.startswith('❌'):
                error_response = {
                    "success": False,
                    "message": analysis,
                    "validation_error": True,
                    "expected_timeframe": "M15"
                }
                print(f"🚨 ANALYZE ENDPOINT: ⚠️ Timeframe validation failed (returning 200): {analysis}")
                return jsonify(error_response), 200

            # ✅ Check length and shorten if needed - UPDATED WITH TIMEFRAME AND CURRENCY
            if len(analysis) > 1024:
                print(f"📏 LENGTH CHECK: First analysis too long ({len(analysis)} chars), shortening...")
                analysis = shorten_analysis_text(analysis, timeframe=timeframe, currency=first_currency)
                print(f"📏 LENGTH CHECK: After shortening: {len(analysis)} chars")

            session_data['first_analysis'] = analysis
            session_data['first_timeframe'] = timeframe
            session_data['first_currency'] = first_currency
            session_data['status'] = 'first_done'

            response_data = {
                "success": True,
                "message": f"✅ تم تحليل {timeframe} لـ {first_currency} بنجاح",
                "analysis": analysis,
                "next_action": "second_analysis",
                "next_prompt": f"الآن أرسل صورة الإطار الزمني الثاني (H4) لنفس العملة ({first_currency})"
            }

            # Final logging before sending to SendPulse
            print(f"🔍 FINAL RESPONSE TO SENDPULSE - {action_type.upper()}")
            print(f"📊 Analysis length: {len(analysis)} characters")
            print(f"📋 Final analysis preview: {analysis[:100]}...")
            print(f"🔚 Final analysis ending: ...{analysis[-100:] if len(analysis) > 100 else analysis}")
            print(f"🔍 FINAL CHECK BEFORE SENDPULSE:")
            print(f"📊 Response data size: {len(str(response_data))} characters")
            print(f"📊 Analysis field size: {len(analysis)} characters")
            print(f"🚀 Sending to SendPulse...")

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
                return jsonify(error_response), 200

            if session_data['status'] != 'first_done':
                error_response = {
                    "success": False,
                    "message": "يجب تحليل الإطار الأول قبل الثاني"
                }
                print(f"🚨 ANALYZE ENDPOINT: ❌ Returning error - First analysis not done: {error_response}")
                return jsonify(error_response), 200

            # Use H4 for second analysis
            second_timeframe = 'H4'
            
            # Detect currency from second image
            print(f"🪙 ANALYZE ENDPOINT: Detecting currency from second image...")
            second_currency, currency_error = detect_currency_from_image(image_str, image_format)
            print(f"🪙 ANALYZE ENDPOINT: Second currency detected: {second_currency}")
            
            # Validate currency consistency
            first_currency = session_data.get('first_currency')
            if first_currency:
                is_currency_valid, currency_error_msg = validate_currency_consistency(first_currency, second_currency)
                if not is_currency_valid:
                    error_response = {
                        "success": False,
                        "message": currency_error_msg,
                        "validation_error": True,
                        "expected_currency": first_currency
                    }
                    print(f"🚨 ANALYZE ENDPOINT: ⚠️ Currency validation failed (returning 200): {currency_error_msg}")
                    return jsonify(error_response), 200

            print(f"🚨 ANALYZE ENDPOINT: 🧠 Starting second analysis with timeframe: {second_timeframe}")
            
            # Pass currency pair to analysis for proper stop loss rules
            analysis = analyze_with_openai(image_str, image_format, second_timeframe, session_data['first_analysis'], action_type='second_analysis', currency_pair=second_currency)

            # Check if analysis returned a validation error (starts with ❌)
            if analysis.startswith('❌'):
                error_response = {
                    "success": False,
                    "message": analysis,
                    "validation_error": True,
                    "expected_timeframe": "H4"
                }
                print(f"🚨 ANALYZE ENDPOINT: ⚠️ Timeframe validation failed (returning 200): {analysis}")
                return jsonify(error_response), 200

            # ✅ Check length and shorten if needed - UPDATED WITH TIMEFRAME AND CURRENCY
            if len(analysis) > 1024:
                print(f"📏 LENGTH CHECK: Second analysis too long ({len(analysis)} chars), shortening...")
                analysis = shorten_analysis_text(analysis, timeframe=second_timeframe, currency=second_currency)
                print(f"📏 LENGTH CHECK: After shortening: {len(analysis)} chars")

            session_data['second_analysis'] = analysis
            session_data['second_timeframe'] = second_timeframe
            session_data['second_currency'] = second_currency
            session_data['status'] = 'both_done'

            print(f"🚨 ANALYZE ENDPOINT: 🧠 Generating final combined analysis")
            # Generate final combined analysis with currency info
            final_currency = second_currency or session_data.get('first_currency')
            final_analysis = analyze_with_openai(
                None, None, "combined",
                f"{session_data['first_timeframe']}: {session_data['first_analysis']}",
                session_data['second_analysis'], "final_analysis",
                currency_pair=final_currency
            )

            # ✅ Check length and shorten if needed - UPDATED WITH TIMEFRAME AND CURRENCY
            if len(final_analysis) > 1024:
                print(f"📏 LENGTH CHECK: Final analysis too long ({len(final_analysis)} chars), shortening...")
                final_analysis = shorten_analysis_text(final_analysis, timeframe="مدمج", currency=final_currency)
                print(f"📏 LENGTH CHECK: After shortening: {len(final_analysis)} chars")

            response_data = {
                "success": True,
                "message": f"✅ تم التحليل الشامل لـ {second_currency} بنجاح",
                "analysis": final_analysis,
                "next_action": "user_analysis",
                "next_prompt": "هل تريد مشاركة تحليلك الشخصي للحصول على تقييم؟"
            }

            # Final logging before sending to SendPulse
            print(f"🔍 FINAL RESPONSE TO SENDPULSE - {action_type.upper()}")
            print(f"📊 Analysis length: {len(final_analysis)} characters")
            print(f"📋 Final analysis preview: {final_analysis[:100]}...")
            print(f"🔚 Final analysis ending: ...{final_analysis[-100:] if len(final_analysis) > 100 else final_analysis}")
            print(f"🔍 FINAL CHECK BEFORE SENDPULSE:")
            print(f"📊 Response data size: {len(str(response_data))} characters")
            print(f"📊 Analysis field size: {len(final_analysis)} characters")
            print(f"🚀 Sending to SendPulse...")

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

            # ✅ Check length and shorten if needed (no timeframe/currency for user analysis)
            if len(feedback) > 1024:
                print(f"📏 LENGTH CHECK: User feedback too long ({len(feedback)} chars), shortening...")
                feedback = shorten_analysis_text(feedback)
                print(f"📏 LENGTH CHECK: After shortening: {len(feedback)} chars")

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'completed'

            response_data = {
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "next_action": "new_session",
                "next_prompt": "يمكنك بدء تحليل جديد"
            }

            # Final logging before sending to SendPulse
            print(f"🔍 FINAL RESPONSE TO SENDPULSE - {action_type.upper()}")
            print(f"📊 Analysis length: {len(feedback)} characters")
            print(f"📋 Final analysis preview: {feedback[:100]}...")
            print(f"🔚 Final analysis ending: ...{feedback[-100:] if len(feedback) > 100 else feedback}")
            print(f"🔍 FINAL CHECK BEFORE SENDPULSE:")
            print(f"📊 Response data size: {len(str(response_data))} characters")
            print(f"📊 Analysis field size: {len(feedback)} characters")
            print(f"🚀 Sending to SendPulse...")

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
                'first_currency': None,
                'second_currency': None,
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

@api_bp.route('/analyze-single', methods=['POST'])
def analyze_single_image():
    """
    Analyze a single image - automatically detect timeframe and provide enhanced analysis
    Enhanced with SMC concepts and immediate recommendations
    MAX 1024 CHARACTERS FOR SENDPULSE COMPATIBILITY
    """
    try:
        print(f"🚨 ANALYZE-SINGLE: 📥 Received request at {datetime.now()}")

        data = request.get_json()
        print(f"🚨 ANALYZE-SINGLE: 📥 Request data: {data}")

        if not data:
            print("🚨 ANALYZE-SINGLE: ❌ No JSON data provided")
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 200

        image_url = data.get('image_url')
        print(f"🚨 ANALYZE-SINGLE: 🖼️ Image URL: {image_url}")

        if not image_url:
            print("🚨 ANALYZE-SINGLE: ❌ Missing image_url")
            return jsonify({
                "success": False,
                "error": "Missing image_url"
            }), 200

        # Check OpenAI availability
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        print(f"🚨 ANALYZE-SINGLE: 🤖 OpenAI available: {openai_available}")

        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'Unknown error')
            print(f"🚨 ANALYZE-SINGLE: ❌ OpenAI unavailable: {openai_error}")
            return jsonify({
                "success": False,
                "error": "OpenAI service unavailable",
                "message": openai_error
            }), 200

        # Load and encode image
        print(f"🚨 ANALYZE-SINGLE: 📥 Loading image from URL...")
        image_str, image_format = load_image_from_url(image_url)
        print(f"🚨 ANALYZE-SINGLE: 🖼️ Image loaded - String: {bool(image_str)}, Format: {image_format}")

        if not image_str:
            print("🚨 ANALYZE-SINGLE: ❌ Could not load image from URL")
            return jsonify({
                "success": False,
                "error": "Could not load image from URL"
            }), 200

        # Detect investing.com frame first
        print(f"🚨 ANALYZE-SINGLE: 🔍 Detecting frame type...")
        frame_type, detected_timeframe = detect_investing_frame(image_str, image_format)
        print(f"🚨 ANALYZE-SINGLE: 🔍 Frame type: {frame_type}, Timeframe: {detected_timeframe}")

        # If investing.com detection returned an error message (starts with apology), treat as unknown
        if frame_type and any(word in frame_type.lower() for word in ['sorry', 'apology', 'اسف', 'اعتذر']):
            print(f"🚨 ANALYZE-SINGLE: ⚠️ Investing detection returned error, treating as unknown")
            frame_type = "unknown"
            detected_timeframe = "UNKNOWN"

        # If not investing.com frame or detection failed, use standard detection
        if frame_type == "unknown" or detected_timeframe == "UNKNOWN":
            print(f"🚨 ANALYZE-SINGLE: 🔍 Detecting timeframe from image...")
            detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)
            print(f"🚨 ANALYZE-SINGLE: 🔍 Timeframe detection result: {detected_timeframe}, Error: {detection_error}")

            if detection_error:
                print(f"🚨 ANALYZE-SINGLE: ❌ Timeframe detection failed: {detection_error}")
                return jsonify({
                    "success": False,
                    "error": detection_error
                }), 200

        # Detect currency from image
        print(f"🪙 ANALYZE-SINGLE: Detecting currency from image...")
        detected_currency, currency_error = detect_currency_from_image(image_str, image_format)
        print(f"🪙 ANALYZE-SINGLE: Currency detected: {detected_currency}")

        print(f"🚨 ANALYZE-SINGLE: ✅ Timeframe detected: {detected_timeframe}")

        # Analyze with OpenAI using detected timeframe with enhanced SMC analysis
        print(f"🚨 ANALYZE-SINGLE: 🧠 Starting enhanced analysis with timeframe: {detected_timeframe}")
        
        # Pass currency pair to analysis for proper stop loss rules
        analysis = analyze_with_openai(
        image_str=image_str,
        image_format=image_format,
        timeframe=detected_timeframe,
        action_type="single_analysis",
        currency_pair=detected_currency
        )

        # Enhanced fallback for refusals or very short responses
        if (analysis.startswith('❌') or
        any(word in analysis.lower() for word in ['sorry', 'apology', 'اسف', 'اعتذر', 'لا استطيع', 'عذرًا']) or
        len(analysis) < 100):  # Very short response likely indicates refusal
        print(f"🚨 ANALYZE-SINGLE: ⚠️ Analysis refused or too short, using fallback")
        analysis = analyze_simple_chart_fallback(
        image_str=image_str,
        image_format=image_format,
        timeframe=detected_timeframe,
        currency_pair=detected_currency
    )
        # ✅ Check length and shorten if needed - UPDATED WITH TIMEFRAME AND CURRENCY
        if len(analysis) > 1024:
            print(f"📏 LENGTH CHECK: Single analysis too long ({len(analysis)} chars), shortening...")
            analysis = shorten_analysis_text(analysis, timeframe=detected_timeframe, currency=detected_currency)
            print(f"📏 LENGTH CHECK: After shortening: {len(analysis)} chars")

        print(f"🚨 ANALYZE-SINGLE: ✅ Enhanced analysis completed, length: {len(analysis)} chars")

        response_data = {
            "success": True,
            "analysis": analysis,
            "detected_timeframe": detected_timeframe,
            "detected_currency": detected_currency,
            "frame_type": frame_type,
            "features": ["SMC_Analysis", "Immediate_Recommendations", "Liquidity_Analysis"]
        }

        # Final logging before sending to SendPulse
        print(f"🔍 FINAL RESPONSE TO SENDPULSE - SINGLE_ANALYSIS")
        print(f"📊 Analysis length: {len(analysis)} characters")
        print(f"📋 Final analysis preview: {analysis[:100]}...")
        print(f"🔚 Final analysis ending: ...{analysis[-100:] if len(analysis) > 100 else analysis}")
        print(f"🔍 FINAL CHECK BEFORE SENDPULSE:")
        print(f"📊 Response data size: {len(str(response_data))} characters")
        print(f"📊 Analysis field size: {len(analysis)} characters")
        print(f"🚀 Sending to SendPulse...")

        return jsonify(response_data), 200

    except Exception as e:
        print(f"🚨 ANALYZE-SINGLE: ❌ Exception occurred: {str(e)}")
        import traceback
        print(f"🚨 ANALYZE-SINGLE: ❌ Stack trace: {traceback.format_exc()}")

        return jsonify({
            "success": False,
            "error": f"Analysis failed: {str(e)}"
        }), 200

@api_bp.route('/analyze-technical', methods=['POST'])
def analyze_technical():
    """
    Analyze the chart for technical analysis only
    MAX 1024 CHARACTERS FOR SENDPULSE COMPATIBILITY
    """
    try:
        print(f"🚨 ANALYZE-TECHNICAL: 📥 Received request at {datetime.now()}")

        data = request.get_json()
        print(f"🚨 ANALYZE-TECHNICAL: 📥 Request data: {data}")

        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 200

        image_url = data.get('image_url')
        print(f"🚨 ANALYZE-TECHNICAL: 🖼️ Image URL: {image_url}")

        if not image_url:
            return jsonify({
                "success": False,
                "error": "Missing image_url"
            }), 200

        # Check OpenAI availability
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        print(f"🚨 ANALYZE-TECHNICAL: 🤖 OpenAI available: {openai_available}")

        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'Unknown error')
            return jsonify({
                "success": False,
                "error": "OpenAI service unavailable",
                "message": openai_error
            }), 200

        # Load and encode image
        print(f"🚨 ANALYZE-TECHNICAL: 📥 Loading image from URL...")
        image_str, image_format = load_image_from_url(image_url)
        print(f"🚨 ANALYZE-TECHNICAL: 🖼️ Image loaded - String: {bool(image_str)}, Format: {image_format}")

        if not image_str:
            return jsonify({
                "success": False,
                "error": "Could not load image from URL"
            }), 200

        # Detect investing.com frame first
        print(f"🚨 ANALYZE-TECHNICAL: 🔍 Detecting frame type...")
        frame_type, detected_timeframe = detect_investing_frame(image_str, image_format)
        print(f"🚨 ANALYZE-TECHNICAL: 🔍 Frame type: {frame_type}, Timeframe: {detected_timeframe}")

        # If not investing.com frame, use standard detection
        if frame_type == "unknown":
            print(f"🚨 ANALYZE-TECHNICAL: 🔍 Detecting timeframe from image...")
            detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)
            print(f"🚨 ANALYZE-TECHNICAL: 🔍 Timeframe detection result: {detected_timeframe}, Error: {detection_error}")

            if detection_error:
                return jsonify({
                    "success": False,
                    "error": detection_error
                }), 200

        # Detect currency from image
        print(f"🪙 ANALYZE-TECHNICAL: Detecting currency from image...")
        detected_currency, currency_error = detect_currency_from_image(image_str, image_format)
        print(f"🪙 ANALYZE-TECHNICAL: Currency detected: {detected_currency}")

        print(f"🚨 ANALYZE-TECHNICAL: ✅ Timeframe detected: {detected_timeframe}")

        # Analyze technical chart only with currency info
        print(f"🚨 ANALYZE-TECHNICAL: 🧠 Starting technical analysis with timeframe: {detected_timeframe}")

        analysis = analyze_technical_chart(
            image_str=image_str,
            image_format=image_format,
            timeframe=detected_timeframe,
            currency_pair=detected_currency
        )

        # ✅ Check length and shorten if needed - UPDATED WITH TIMEFRAME AND CURRENCY
        if len(analysis) > 1024:
            print(f"📏 LENGTH CHECK: Technical analysis too long ({len(analysis)} chars), shortening...")
            analysis = shorten_analysis_text(analysis, timeframe=detected_timeframe, currency=detected_currency)
            print(f"📏 LENGTH CHECK: After shortening: {len(analysis)} chars")

        print(f"🚨 ANALYZE-TECHNICAL: ✅ Technical analysis completed, length: {len(analysis)} chars")

        response_data = {
            "success": True,
            "analysis": analysis,
            "detected_timeframe": detected_timeframe,
            "detected_currency": detected_currency,
            "frame_type": frame_type,
            "type": "technical_analysis"
        }

        # Final logging before sending to SendPulse
        print(f"🔍 FINAL RESPONSE TO SENDPULSE - TECHNICAL_ANALYSIS")
        print(f"📊 Analysis length: {len(analysis)} characters")
        print(f"📋 Final analysis preview: {analysis[:100]}...")
        print(f"🔚 Final analysis ending: ...{analysis[-100:] if len(analysis) > 100 else analysis}")
        print(f"🔍 FINAL CHECK BEFORE SENDPULSE:")
        print(f"📊 Response data size: {len(str(response_data))} characters")
        print(f"📊 Analysis field size: {len(analysis)} characters")
        print(f"🚀 Sending to SendPulse...")

        return jsonify(response_data), 200

    except Exception as e:
        print(f"🚨 ANALYZE-TECHNICAL: ❌ Exception occurred: {str(e)}")
        import traceback
        print(f"🚨 ANALYZE-TECHNICAL: ❌ Stack trace: {traceback.format_exc()}")

        return jsonify({
            "success": False,
            "error": f"Technical analysis failed: {str(e)}"
        }), 200

@api_bp.route('/analyze-user-feedback', methods=['POST'])
def analyze_user_feedback():
    """
    Analyze user's drawn analysis and provide feedback
    MAX 1024 CHARACTERS FOR SENDPULSE COMPATIBILITY
    """
    try:
        print(f"🚨 ANALYZE-USER-FEEDBACK: 📥 Received request at {datetime.now()}")

        data = request.get_json()
        print(f"🚨 ANALYZE-USER-FEEDBACK: 📥 Request data: {data}")

        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided"
            }), 200

        image_url = data.get('image_url')
        print(f"🚨 ANALYZE-USER-FEEDBACK: 🖼️ Image URL: {image_url}")

        if not image_url:
            return jsonify({
                "success": False,
                "error": "Missing image_url"
            }), 200

        # Check OpenAI availability
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        print(f"🚨 ANALYZE-USER-FEEDBACK: 🤖 OpenAI available: {openai_available}")

        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'Unknown error')
            return jsonify({
                "success": False,
                "error": "OpenAI service unavailable",
                "message": openai_error
            }), 200

        # Load and encode image
        print(f"🚨 ANALYZE-USER-FEEDBACK: 📥 Loading image from URL...")
        image_str, image_format = load_image_from_url(image_url)
        print(f"🚨 ANALYZE-USER-FEEDBACK: 🖼️ Image loaded - String: {bool(image_str)}, Format: {image_format}")

        if not image_str:
            return jsonify({
                "success": False,
                "error": "Could not load image from URL"
            }), 200

        # Detect timeframe from image
        print(f"🚨 ANALYZE-USER-FEEDBACK: 🔍 Detecting timeframe from image...")
        timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)
        print(f"🚨 ANALYZE-USER-FEEDBACK: 🔍 Timeframe detection result: {timeframe}, Error: {detection_error}")

        if detection_error:
            return jsonify({
                "success": False,
                "error": detection_error
            }), 200

        print(f"🚨 ANALYZE-USER-FEEDBACK: ✅ Timeframe detected: {timeframe}")

        # For user feedback, we don't need technical analysis context
        print(f"🚨 ANALYZE-USER-FEEDBACK: 🧠 Starting user feedback analysis with timeframe: {timeframe}")

        feedback = analyze_user_drawn_feedback_simple(
            image_str=image_str,
            image_format=image_format,
            timeframe=timeframe
        )

        # ✅ Check length and shorten if needed - UPDATED WITH TIMEFRAME
        if len(feedback) > 1024:
            print(f"📏 LENGTH CHECK: User feedback too long ({len(feedback)} chars), shortening...")
            feedback = shorten_analysis_text(feedback, timeframe=timeframe)
            print(f"📏 LENGTH CHECK: After shortening: {len(feedback)} chars")

        print(f"🚨 ANALYZE-USER-FEEDBACK: ✅ User feedback analysis completed, length: {len(feedback)} chars")

        response_data = {
            "success": True,
            "feedback": feedback,
            "detected_timeframe": timeframe,
            "type": "user_feedback"
        }

        # Final logging before sending to SendPulse
        print(f"🔍 FINAL RESPONSE TO SENDPULSE - USER_FEEDBACK")
        print(f"📊 Analysis length: {len(feedback)} characters")
        print(f"📋 Final analysis preview: {feedback[:100]}...")
        print(f"🔚 Final analysis ending: ...{feedback[-100:] if len(feedback) > 100 else feedback}")
        print(f"🔍 FINAL CHECK BEFORE SENDPULSE:")
        print(f"📊 Response data size: {len(str(response_data))} characters")
        print(f"📊 Analysis field size: {len(feedback)} characters")
        print(f"🚀 Sending to SendPulse...")

        return jsonify(response_data), 200

    except Exception as e:
        print(f"🚨 ANALYZE-USER-FEEDBACK: ❌ Exception occurred: {str(e)}")
        import traceback
        print(f"🚨 ANALYZE-USER-FEEDBACK: ❌ Stack trace: {traceback.format_exc()}")

        return jsonify({
            "success": False,
            "error": f"User feedback analysis failed: {str(e)}"
        }), 200

# Keep the old endpoint for backward compatibility
@api_bp.route('/analyze-user-drawn', methods=['POST'])
def analyze_user_drawn():
    """
    Legacy endpoint - kept for backward compatibility
    """
    return jsonify({
        "success": False,
        "error": "This endpoint is deprecated. Please use /analyze-technical and /analyze-user-feedback instead."
    }), 200
