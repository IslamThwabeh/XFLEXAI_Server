# routes/api_routes.py
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from services.openai_service import (
    get_technical_analysis,
    get_trading_recommendations,
    get_user_feedback,
    load_image_from_url,
    detect_timeframe_from_image,
    detect_currency_from_image,
    validate_currency_consistency,
    detect_investing_frame,
    extract_investing_data
)

from database.operations import get_user_by_telegram_id, redeem_registration_key

api_bp = Blueprint('api_bp', __name__)
analysis_sessions = {}

@api_bp.route('/')
def home():
    openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
    openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'خطأ غير معروف')
    status = "✅" if openai_available else "❌"
    return f"خادم XFLEXAI يعمل {status} - OpenAI: {'متوفر' if openai_available else openai_error}"

@api_bp.route('/redeem-key', methods=['POST'])
def redeem_key_route():
    """
    نقطة النهاية لاستبدال مفتاح التسجيل.
    JSON المتوقع: { "telegram_user_id": 123456789, "key": "ABC123" }
    يُرجع success أو error JSON مع expiry_date في حالة النجاح.
    """
    data = request.get_json() or {}
    telegram_user_id = data.get('telegram_user_id')
    key_value = data.get('key')

    if not telegram_user_id or not key_value:
        return jsonify({"success": False, "error": "telegram_user_id و key مطلوبان"}), 400

    result = redeem_registration_key(key_value, telegram_user_id)
    if not result.get('success'):
        return jsonify(result), 400

    return jsonify(result), 200

@api_bp.route('/analyze', methods=['POST'])
def analyze():
    """
    نقطة نهاية تحليل مبسطة - تتعامل مع جميع أنواع التحليل
    أنواع الإجراءات: first_analysis, second_analysis, user_analysis, new_session
    جميع الردود محدودة بـ 1024 حرف لـ SENDPULSE
    """
    try:
        # تسجيل الطلب الوارد
        print(f"🚨 نقطة نهاية التحليل: تم استلام الطلب في {datetime.now()}")
        print(f"🚨 نقطة نهاية التحليل: الرؤوس: {dict(request.headers)}")
        print(f"🚨 نقطة نهاية التحليل: نوع المحتوى: {request.content_type}")

        if not request.is_json:
            error_response = {
                "success": False,
                "message": "نوع المحتوى غير مدعوم",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - ليس JSON: {error_response}")
            return jsonify(error_response), 415

        data = request.get_json()
        print(f"🚨 نقطة نهاية التحليل: 📥 تم استلام بيانات JSON: {data}")

        if not data:
            error_response = {
                "success": False,
                "message": "لم يتم إرسال بيانات",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - لا توجد بيانات: {error_response}")
            return jsonify(error_response), 400

        telegram_user_id = data.get('telegram_user_id')
        action_type = data.get('action_type', 'first_analysis')
        image_url = data.get('image_url')

        print(f"🚨 نقطة نهاية التحليل: 👤 معرف التليجرام: {telegram_user_id}")
        print(f"🚨 نقطة نهاية التحليل: 🎯 نوع الإجراء: {action_type}")
        print(f"🚨 نقطة نهاية التحليل: 🖼️ رابط الصورة: {image_url}")

        if not telegram_user_id:
            error_response = {
                "success": False,
                "code": "missing_telegram_id",
                "message": "يرجى تضمين telegram_user_id الخاص بك",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - معرف تليجرام مفقود: {error_response}")
            return jsonify(error_response), 400

        # التأكد من أن telegram_user_id رقمي
        try:
            telegram_user_id = int(telegram_user_id)
        except Exception:
            error_response = {
                "success": False, 
                "message": "معرف تليجرام غير صالح",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - معرف تليجرام غير صالح: {error_response}")
            return jsonify(error_response), 400

        # التحقق من حالة تسجيل المستخدم
        user = get_user_by_telegram_id(telegram_user_id)
        if not user:
            error_response = {
                "success": False,
                "code": "not_registered",
                "message": "حسابك غير مسجل. يرجى إرسال مفتاح التسجيل الخاص بك باستخدام /redeem-key",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - المستخدم غير مسجل: {error_response}")
            return jsonify(error_response), 403

        # التحقق من انتهاء الصلاحية
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
                "message": "انتهت صلاحية اشتراكك. يرجى التجديد أو الاتصال بالمسؤول.",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - انتهت صلاحية الاشتراك: {error_response}")
            return jsonify(error_response), 403

        # التحقق من توفر OpenAI باستخدام current_app.config
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'خطأ غير معروف')
            error_response = {
                "success": False,
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": openai_error,
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - OpenAI غير متوفر: {error_response}")
            return jsonify(error_response), 503

        # تهيئة أو الحصول على الجلسة
        if telegram_user_id not in analysis_sessions:
            analysis_sessions[telegram_user_id] = {
                'first_analysis': None,
                'first_recommendations': None,
                'second_analysis': None,
                'second_recommendations': None,
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

        print(f"🚨 نقطة نهاية التحليل: 💾 بيانات الجلسة: {session_data}")

        # تحميل الصورة إذا تم توفيرها
        image_str, image_format = None, None
        if image_url:
            print(f"🚨 نقطة نهاية التحليل: 📥 جاري تحميل الصورة من الرابط: {image_url}")
            image_str, image_format = load_image_from_url(image_url)
            print(f"🚨 نقطة نهاية التحليل: 🖼️ تم تحميل الصورة - السلسلة: {bool(image_str)}، التنسيق: {image_format}")

        # التعامل مع أنواع الإجراءات المختلفة
        if action_type == 'first_analysis':
            if not image_str:
                error_response = {
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "",
                    "recommendations": ""
                }
                print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - صورة غير صالحة: {error_response}")
                return jsonify(error_response), 200

            print(f"🚨 نقطة نهاية التحليل: 🧠 بدء التحليل الأول مع الإطار الزمني: {timeframe}")
            
            # كشف العملة من الصورة الأولى
            print(f"🪙 نقطة نهاية التحليل: جاري كشف العملة من الصورة الأولى...")
            first_currency, currency_error = detect_currency_from_image(image_str, image_format)
            print(f"🪙 نقطة نهاية التحليل: العملة الأولى المكتشفة: {first_currency}")
            
            # المكالمة الأولى: الحصول على التحليل الفني فقط
            print(f"📞 المكالمة API 1: جاري الحصول على التحليل الفني...")
            analysis = get_technical_analysis(
                image_str, image_format, timeframe, 
                action_type='first_analysis', 
                currency_pair=first_currency
            )

            # التحقق مما إذا كان التحليل أعاد خطأ تحقق (يبدأ بـ ❌)
            if analysis.startswith('❌'):
                error_response = {
                    "success": False,
                    "message": analysis,
                    "analysis": "",
                    "recommendations": "",
                    "validation_error": True,
                    "expected_timeframe": "M15"
                }
                print(f"🚨 نقطة نهاية التحليل: ⚠️ فشل تحقق الإطار الزمني: {analysis}")
                return jsonify(error_response), 200

            # المكالمة الثانية: الحصول على توصيات التداول فقط
            print(f"📞 المكالمة API 2: جاري الحصول على توصيات التداول...")
            recommendations = get_trading_recommendations(
                analysis, image_str, image_format, timeframe, first_currency, 'first_analysis'
            )

            session_data['first_analysis'] = analysis
            session_data['first_recommendations'] = recommendations
            session_data['first_timeframe'] = timeframe
            session_data['first_currency'] = first_currency
            session_data['status'] = 'first_done'

            response_data = {
                "success": True,
                "message": f"✅ تم تحليل {timeframe} لـ {first_currency} بنجاح",
                "analysis": analysis,
                "recommendations": recommendations,
                "next_action": "second_analysis",
                "next_prompt": f"الآن أرسل صورة الإطار الزمني الثاني (H4) لنفس العملة ({first_currency})"
            }

            # التسجيل النهائي قبل الإرسال إلى SendPulse
            print(f"🔍 الرد النهائي لـ SENDPULSE - FIRST_ANALYSIS")
            print(f"📊 طول التحليل: {len(analysis)} حرف")
            print(f"📊 طول التوصيات: {len(recommendations)} حرف")
            print(f"📋 معاينة التحليل النهائي: {analysis[:100]}...")
            print(f"📋 معاينة التوصيات النهائية: {recommendations[:100]}...")
            print(f"🔍 الفحص النهائي قبل SENDPULSE:")
            print(f"📊 حجم بيانات الرد: {len(str(response_data))} حرف")
            print(f"📊 حجم حقل التحليل: {len(analysis)} حرف")
            print(f"📊 حجم حقل التوصيات: {len(recommendations)} حرف")
            print(f"🚀 جاري الإرسال إلى SendPulse...")

            print(f"🚨 نقطة نهاية التحليل: ✅ اكتمل التحليل الأول - الرد: {response_data}")
            return jsonify(response_data), 200

        elif action_type == 'second_analysis':
            print(f"🚨 نقطة نهاية التحليل: 🔄 بدء التحليل الثاني")

            if not image_str:
                error_response = {
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "",
                    "recommendations": ""
                }
                print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - صورة غير صالحة: {error_response}")
                return jsonify(error_response), 200

            if session_data['status'] != 'first_done':
                error_response = {
                    "success": False,
                    "message": "يجب تحليل الإطار الأول قبل الثاني",
                    "analysis": "",
                    "recommendations": ""
                }
                print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - التحليل الأول لم يكتمل: {error_response}")
                return jsonify(error_response), 200

            # استخدام H4 للتحليل الثاني
            second_timeframe = 'H4'
            
            # كشف العملة من الصورة الثانية
            print(f"🪙 نقطة نهاية التحليل: جاري كشف العملة من الصورة الثانية...")
            second_currency, currency_error = detect_currency_from_image(image_str, image_format)
            print(f"🪙 نقطة نهاية التحليل: العملة الثانية المكتشفة: {second_currency}")
            
            # التحقق من تطابق العملة
            first_currency = session_data.get('first_currency')
            if first_currency:
                is_currency_valid, currency_error_msg = validate_currency_consistency(first_currency, second_currency)
                if not is_currency_valid:
                    error_response = {
                        "success": False,
                        "message": currency_error_msg,
                        "analysis": "",
                        "recommendations": "",
                        "validation_error": True,
                        "expected_currency": first_currency
                    }
                    print(f"🚨 نقطة نهاية التحليل: ⚠️ فشل تحقق العملة: {currency_error_msg}")
                    return jsonify(error_response), 200

            # المكالمة الأولى: الحصول على التحليل الفني فقط لـ H4
            print(f"📞 المكالمة API 1: جاري الحصول على التحليل الفني لـ H4...")
            analysis = get_technical_analysis(
                image_str, image_format, second_timeframe, 
                session_data['first_analysis'], 
                action_type='second_analysis', 
                currency_pair=second_currency
            )

            # التحقق مما إذا كان التحليل أعاد خطأ تحقق (يبدأ بـ ❌)
            if analysis.startswith('❌'):
                error_response = {
                    "success": False,
                    "message": analysis,
                    "analysis": "",
                    "recommendations": "",
                    "validation_error": True,
                    "expected_timeframe": "H4"
                }
                print(f"🚨 نقطة نهاية التحليل: ⚠️ فشل تحقق الإطار الزمني: {analysis}")
                return jsonify(error_response), 200

            # المكالمة الثانية: الحصول على توصيات التداول لـ H4
            print(f"📞 المكالمة API 2: جاري الحصول على توصيات التداول لـ H4...")
            recommendations = get_trading_recommendations(
                analysis, image_str, image_format, second_timeframe, second_currency, 'second_analysis'
            )

            session_data['second_analysis'] = analysis
            session_data['second_recommendations'] = recommendations
            session_data['second_timeframe'] = second_timeframe
            session_data['second_currency'] = second_currency
            session_data['status'] = 'both_done'

            # للتحليل النهائي، يمكننا أيضًا إجراء مكالمتين منفصلتين إذا لزم الأمر
            print(f"🚨 نقطة نهاية التحليل: 🧠 جاري إنشاء التحليل النهائي المجمع")
            final_currency = second_currency or session_data.get('first_currency')
            
            # للتحليل النهائي، سنستخدم التحليلات الموجودة لإنشاء توصيات نهائية
            combined_analysis = f"تحليل M15: {session_data['first_analysis']}\n\nتحليل H4: {analysis}"
            
            # الحصول على التوصيات النهائية بناءً على التحليل المجمع
            print(f"📞 المكالمة API 3: جاري الحصول على التوصيات النهائية...")
            final_recommendations = get_trading_recommendations(
                combined_analysis, None, None, "مدمج", final_currency, 'final_analysis'
            )

            response_data = {
                "success": True,
                "message": f"✅ تم التحليل الشامل لـ {second_currency} بنجاح",
                "analysis": combined_analysis[:1024],  # التأكد من عدم تجاوز الحد
                "recommendations": final_recommendations,
                "next_action": "user_analysis",
                "next_prompt": "هل تريد مشاركة تحليلك الشخصي للحصول على تقييم؟"
            }

            print(f"🔍 الرد النهائي لـ SENDPULSE - SECOND_ANALYSIS")
            print(f"📊 طول التحليل: {len(combined_analysis)} حرف")
            print(f"📊 طول التوصيات: {len(final_recommendations)} حرف")
            print(f"📋 معاينة التحليل النهائي: {combined_analysis[:100]}...")
            print(f"📋 معاينة التوصيات النهائية: {final_recommendations[:100]}...")
            print(f"🔍 الفحص النهائي قبل SENDPULSE:")
            print(f"📊 حجم بيانات الرد: {len(str(response_data))} حرف")
            print(f"📊 حجم حقل التحليل: {len(combined_analysis)} حرف")
            print(f"📊 حجم حقل التوصيات: {len(final_recommendations)} حرف")
            print(f"🚀 جاري الإرسال إلى SendPulse...")

            return jsonify(response_data), 200

        elif action_type == 'user_analysis':
            print(f"🚨 نقطة نهاية التحليل: 👤 بدء تقييم تحليل المستخدم")

            if not user_analysis_text:
                error_response = {
                    "success": False,
                    "message": "تحليل نصي مطلوب",
                    "analysis": "",
                    "recommendations": ""
                }
                print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - لا يوجد تحليل مستخدم: {error_response}")
                return jsonify(error_response), 400

            # مكالمة واحدة لتقييم المستخدم (تجمع بين التحليل والتقييم)
            feedback, empty_recommendations = get_user_feedback(user_analysis_text)

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'completed'

            response_data = {
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "recommendations": "",  # فارغ لتقييم المستخدم
                "next_action": "new_session",
                "next_prompt": "يمكنك بدء تحليل جديد"
            }

            print(f"🔍 الرد النهائي لـ SENDPULSE - USER_ANALYSIS")
            print(f"📊 طول التحليل: {len(feedback)} حرف")
            print(f"🚀 جاري الإرسال إلى SendPulse...")

            return jsonify(response_data), 200

        elif action_type == 'new_session':
            print(f"🚨 نقطة نهاية التحليل: 🔄 بدء جلسة جديدة")
            # إعادة تعيين الجلسة ولكن الاحتفاظ بسجل المحادثة إذا لزم الأمر
            analysis_sessions[telegram_user_id] = {
                'first_analysis': None,
                'first_recommendations': None,
                'second_analysis': None,
                'second_recommendations': None,
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
                "analysis": "",
                "recommendations": "",
                "next_action": "first_analysis",
                "next_prompt": "أرسل صورة الرسم البياني الأول للتحليل"
            }
            print(f"🚨 نقطة نهاية التحليل: ✅ بدأت جلسة جديدة - الرد: {response_data}")
            return jsonify(response_data), 200

        else:
            error_response = {
                "success": False,
                "message": "نوع إجراء غير معروف",
                "analysis": "",
                "recommendations": ""
            }
            print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ - نوع إجراء غير معروف: {error_response}")
            return jsonify(error_response), 400

    except Exception as e:
        error_response = {
            "success": False,
            "message": f"خطأ أثناء المعالجة: {str(e)}",
            "analysis": "",
            "recommendations": ""
        }
        print(f"🚨 نقطة نهاية التحليل: ❌ حدث استثناء: {str(e)}")
        print(f"🚨 نقطة نهاية التحليل: ❌ إرجاع خطأ: {error_response}")
        return jsonify(error_response), 400

@api_bp.route('/status')
def status_route():
    openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
    return jsonify({
        "server": "يعمل",
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
    تحليل صورة واحدة - اكتشاف الإطار الزمني تلقائيًا وتقديم تحليل محسن
    محسن بمفاهيم SMC والتوصيات الفورية
    الحد الأقصى 1024 حرف لتوافق SENDPULSE
    """
    try:
        print(f"🚨 تحليل-منفرد: 📥 تم استلام الطلب في {datetime.now()}")

        data = request.get_json()
        print(f"🚨 تحليل-منفرد: 📥 بيانات الطلب: {data}")

        if not data:
            print("🚨 تحليل-منفرد: ❌ لم يتم توفير بيانات JSON")
            return jsonify({
                "success": False,
                "error": "لم يتم توفير بيانات JSON",
                "analysis": "",
                "recommendations": ""
            }), 200

        image_url = data.get('image_url')
        print(f"🚨 تحليل-منفرد: 🖼️ رابط الصورة: {image_url}")

        if not image_url:
            print("🚨 تحليل-منفرد: ❌ رابط الصورة مفقود")
            return jsonify({
                "success": False,
                "error": "رابط الصورة مفقود",
                "analysis": "",
                "recommendations": ""
            }), 200

        # التحقق من توفر OpenAI
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        print(f"🚨 تحليل-منفرد: 🤖 OpenAI متوفر: {openai_available}")

        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'خطأ غير معروف')
            print(f"🚨 تحليل-منفرد: ❌ OpenAI غير متوفر: {openai_error}")
            return jsonify({
                "success": False,
                "error": "خدمة OpenAI غير متوفرة",
                "message": openai_error,
                "analysis": "",
                "recommendations": ""
            }), 200

        # تحميل وتشفير الصورة
        print(f"🚨 تحليل-منفرد: 📥 جاري تحميل الصورة من الرابط...")
        image_str, image_format = load_image_from_url(image_url)
        print(f"🚨 تحليل-منفرد: 🖼️ تم تحميل الصورة - السلسلة: {bool(image_str)}، التنسيق: {image_format}")

        if not image_str:
            print("🚨 تحليل-منفرد: ❌ تعذر تحميل الصورة من الرابط")
            return jsonify({
                "success": False,
                "error": "تعذر تحميل الصورة من الرابط",
                "analysis": "",
                "recommendations": ""
            }), 200

        # كشف إطار investing.com أولاً
        print(f"🚨 تحليل-منفرد: 🔍 جاري كشف نوع الإطار...")
        frame_type, detected_timeframe = detect_investing_frame(image_str, image_format)
        print(f"🚨 تحليل-منفرد: 🔍 نوع الإطار: {frame_type}، الإطار الزمني: {detected_timeframe}")

        # إذا أعاد كشف investing.com رسالة خطأ (تبدأ باعتذار)، عالج كغير معروف
        if frame_type and any(word in frame_type.lower() for word in ['sorry', 'apology', 'اسف', 'اعتذر']):
            print(f"🚨 تحليل-منفرد: ⚠️ أعاد كشف investing خطأ، جاري التعامل كغير معروف")
            frame_type = "unknown"
            detected_timeframe = "UNKNOWN"

        # إذا لم يكن إطار investing.com أو فشل الكشف، استخدم الكشف القياسي
        if frame_type == "unknown" or detected_timeframe == "UNKNOWN":
            print(f"🚨 تحليل-منفرد: 🔍 جاري كشف الإطار الزمني من الصورة...")
            detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)
            print(f"🚨 تحليل-منفرد: 🔍 نتيجة كشف الإطار الزمني: {detected_timeframe}، الخطأ: {detection_error}")

            if detection_error:
                print(f"🚨 تحليل-منفرد: ❌ فشل كشف الإطار الزمني: {detection_error}")
                return jsonify({
                    "success": False,
                    "error": detection_error,
                    "analysis": "",
                    "recommendations": ""
                }), 200

        # كشف العملة من الصورة
        print(f"🪙 تحليل-منفرد: جاري كشف العملة من الصورة...")
        detected_currency, currency_error = detect_currency_from_image(image_str, image_format)
        print(f"🪙 تحليل-منفرد: العملة المكتشفة: {detected_currency}")

        print(f"🚨 تحليل-منفرد: ✅ تم كشف الإطار الزمني: {detected_timeframe}")

        # المكالمة الأولى: الحصول على التحليل الفني فقط
        print(f"📞 المكالمة API 1: جاري الحصول على التحليل الفني...")
        analysis = get_technical_analysis(
            image_str=image_str,
            image_format=image_format,
            timeframe=detected_timeframe,
            action_type="single_analysis",
            currency_pair=detected_currency
        )

        # المكالمة الثانية: الحصول على توصيات التداول فقط
        print(f"📞 المكالمة API 2: جاري الحصول على توصيات التداول...")
        recommendations = get_trading_recommendations(
            analysis, image_str, image_format, detected_timeframe, detected_currency, 'single_analysis'
        )

        print(f"🚨 تحليل-منفرد: ✅ اكتمل التحليل المحسن، طول التحليل: {len(analysis)} حرف، طول التوصيات: {len(recommendations)} حرف")

        response_data = {
            "success": True,
            "analysis": analysis,
            "recommendations": recommendations,
            "detected_timeframe": detected_timeframe,
            "detected_currency": detected_currency,
            "frame_type": frame_type,
            "features": ["SMC_Analysis", "Immediate_Recommendations", "Liquidity_Analysis"]
        }

        # التسجيل النهائي قبل الإرسال إلى SendPulse
        print(f"🔍 الرد النهائي لـ SENDPULSE - SINGLE_ANALYSIS")
        print(f"📊 طول التحليل: {len(analysis)} حرف")
        print(f"📊 طول التوصيات: {len(recommendations)} حرف")
        print(f"📋 معاينة التحليل النهائي: {analysis[:100]}...")
        print(f"📋 معاينة التوصيات النهائية: {recommendations[:100]}...")
        print(f"🔍 الفحص النهائي قبل SENDPULSE:")
        print(f"📊 حجم بيانات الرد: {len(str(response_data))} حرف")
        print(f"📊 حجم حقل التحليل: {len(analysis)} حرف")
        print(f"📊 حجم حقل التوصيات: {len(recommendations)} حرف")
        print(f"🚀 جاري الإرسال إلى SendPulse...")

        return jsonify(response_data), 200

    except Exception as e:
        print(f"🚨 تحليل-منفرد: ❌ حدث استثناء: {str(e)}")
        import traceback
        print(f"🚨 تحليل-منفرد: ❌ تتبع المكدس: {traceback.format_exc()}")

        return jsonify({
            "success": False,
            "error": f"فشل التحليل: {str(e)}",
            "analysis": "",
            "recommendations": ""
        }), 200

@api_bp.route('/analyze-technical', methods=['POST'])
def analyze_technical():
    """
    تحليل المخطط للتحليل الفني فقط
    الحد الأقصى 1024 حرف لتوافق SENDPULSE
    """
    try:
        print(f"🚨 تحليل-فني: 📥 تم استلام الطلب في {datetime.now()}")

        data = request.get_json()
        print(f"🚨 تحليل-فني: 📥 بيانات الطلب: {data}")

        if not data:
            return jsonify({
                "success": False,
                "error": "لم يتم توفير بيانات JSON",
                "analysis": "",
                "recommendations": ""
            }), 200

        image_url = data.get('image_url')
        print(f"🚨 تحليل-فني: 🖼️ رابط الصورة: {image_url}")

        if not image_url:
            return jsonify({
                "success": False,
                "error": "رابط الصورة مفقود",
                "analysis": "",
                "recommendations": ""
            }), 200

        # التحقق من توفر OpenAI
        openai_available = current_app.config.get('OPENAI_AVAILABLE', False)
        print(f"🚨 تحليل-فني: 🤖 OpenAI متوفر: {openai_available}")

        if not openai_available:
            openai_error = current_app.config.get('OPENAI_ERROR_MESSAGE', 'خطأ غير معروف')
            return jsonify({
                "success": False,
                "error": "خدمة OpenAI غير متوفرة",
                "message": openai_error,
                "analysis": "",
                "recommendations": ""
            }), 200

        # تحميل وتشفير الصورة
        print(f"🚨 تحليل-فني: 📥 جاري تحميل الصورة من الرابط...")
        image_str, image_format = load_image_from_url(image_url)
        print(f"🚨 تحليل-فني: 🖼️ تم تحميل الصورة - السلسلة: {bool(image_str)}، التنسيق: {image_format}")

        if not image_str:
            return jsonify({
                "success": False,
                "error": "تعذر تحميل الصورة من الرابط",
                "analysis": "",
                "recommendations": ""
            }), 200

        # كشف إطار investing.com أولاً
        print(f"🚨 تحليل-فني: 🔍 جاري كشف نوع الإطار...")
        frame_type, detected_timeframe = detect_investing_frame(image_str, image_format)
        print(f"🚨 تحليل-فني: 🔍 نوع الإطار: {frame_type}، الإطار الزمني: {detected_timeframe}")

        # إذا لم يكن إطار investing.com، استخدم الكشف القياسي
        if frame_type == "unknown":
            print(f"🚨 تحليل-فني: 🔍 جاري كشف الإطار الزمني من الصورة...")
            detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)
            print(f"🚨 تحليل-فني: 🔍 نتيجة كشف الإطار الزمني: {detected_timeframe}، الخطأ: {detection_error}")

            if detection_error:
                return jsonify({
                    "success": False,
                    "error": detection_error,
                    "analysis": "",
                    "recommendations": ""
                }), 200

        # كشف العملة من الصورة
        print(f"🪙 تحليل-فني: جاري كشف العملة من الصورة...")
        detected_currency, currency_error = detect_currency_from_image(image_str, image_format)
        print(f"🪙 تحليل-فني: العملة المكتشفة: {detected_currency}")

        print(f"🚨 تحليل-فني: ✅ تم كشف الإطار الزمني: {detected_timeframe}")

        # المكالمة الأولى: الحصول على التحليل الفني فقط
        print(f"📞 المكالمة API 1: جاري الحصول على التحليل الفني...")
        analysis = get_technical_analysis(
            image_str=image_str,
            image_format=image_format,
            timeframe=detected_timeframe,
            action_type="technical_analysis",
            currency_pair=detected_currency
        )

        # المكالمة الثانية: الحصول على توصيات التداول فقط
        print(f"📞 المكالمة API 2: جاري الحصول على توصيات التداول...")
        recommendations = get_trading_recommendations(
            analysis, image_str, image_format, detected_timeframe, detected_currency, 'technical_analysis'
        )

        print(f"🚨 تحليل-فني: ✅ اكتمل التحليل الفني، طول التحليل: {len(analysis)} حرف، طول التوصيات: {len(recommendations)} حرف")

        response_data = {
            "success": True,
            "analysis": analysis,
            "recommendations": recommendations,
            "detected_timeframe": detected_timeframe,
            "detected_currency": detected_currency,
            "frame_type": frame_type,
            "type": "technical_analysis"
        }

        # التسجيل النهائي قبل الإرسال إلى SendPulse
        print(f"🔍 الرد النهائي لـ SENDPULSE - TECHNICAL_ANALYSIS")
        print(f"📊 طول التحليل: {len(analysis)} حرف")
        print(f"📊 طول التوصيات: {len(recommendations)} حرف")
        print(f"📋 معاينة التحليل النهائي: {analysis[:100]}...")
        print(f"📋 معاينة التوصيات النهائية: {recommendations[:100]}...")
        print(f"🔍 الفحص النهائي قبل SENDPULSE:")
        print(f"📊 حجم بيانات الرد: {len(str(response_data))} حرف")
        print(f"📊 حجم حقل التحليل: {len(analysis)} حرف")
        print(f"📊 حجم حقل التوصيات: {len(recommendations)} حرف")
        print(f"🚀 جاري الإرسال إلى SendPulse...")

        return jsonify(response_data), 200

    except Exception as e:
        print(f"🚨 تحليل-فني: ❌ حدث استثناء: {str(e)}")
        import traceback
        print(f"🚨 تحليل-فني: ❌ تتبع المكدس: {traceback.format_exc()}")

        return jsonify({
            "success": False,
            "error": f"فشل التحليل الفني: {str(e)}",
            "analysis": "",
            "recommendations": ""
        }), 200

# نقطة النهاية القديمة للتوافق مع الإصدارات السابقة
@api_bp.route('/analyze-user-drawn', methods=['POST'])
def analyze_user_drawn():
    """
    نقطة نهاية قديمة - محفوظة للتوافق مع الإصدارات السابقة
    """
    return jsonify({
        "success": False,
        "error": "تم إهمال نقطة النهاية هذه. يرجى استخدام /analyze-technical و /analyze-user-feedback بدلاً من ذلك.",
        "analysis": "",
        "recommendations": ""
    }), 200
