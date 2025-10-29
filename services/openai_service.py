import time
import base64
import requests
import os
from PIL import Image
from io import BytesIO
from config import Config

OPENAI_AVAILABLE = False
client = None
openai_error_message = ""
openai_last_check = 0

def log_openai_response(action_type, response_content, char_limit=1024):
    """
    تسجيل شامل لردود OpenAI
    """
    print(f"\n{'='*80}")
    print(f"🚨 OPENAI RESPONSE LOG - {action_type.upper()}")
    print(f"{'='*80}")
    print(f"📊 طول الرد: {len(response_content)} حرف")
    print(f"📏 الحد الأقصى: {char_limit} حرف")
    print(f"📈 تجاوز الحد: {len(response_content) > char_limit}")
    print(f"📋 محتوى الرد الكامل:")
    print(f"{'='*40}")
    print(response_content)
    print(f"{'='*40}")
    print(f"🔍 نهاية الرد: ...{response_content[-50:] if len(response_content) > 50 else response_content}")
    print(f"{'='*80}\n")

def check_recommendations(action_type, analysis_text):
    """
    التحقق من احتواء التحليل على التوصيات الأساسية
    """
    print(f"\n🔍 فحص التوصيات - {action_type.upper()}")

    # الكلمات المفتاحية للتحقق منها
    recommendation_keywords = [
        'توصية', 'توصيات', 'دخول', 'شراء', 'بيع', 'هدف', 'أهداف', 'وقف', 'خسارة',
        'نقطة', 'نقاط', 'مخاطرة', 'عائد', 'الدخول عند', 'البيع عند', 'الشراء عند'
    ]

    has_recommendation = any(keyword in analysis_text for keyword in recommendation_keywords)

    print(f"📊 يحتوي على توصيات: {has_recommendation}")
    print(f"📝 فحص التوصيات: {'✅ نجح' if has_recommendation else '⚠️ فشل'}")

    if not has_recommendation:
        print("⚠️ تحذير: التحليل يفتقد توصيات التداول!")

    return has_recommendation

def init_openai():
    """
    تهيئة عميل OpenAI واختبار توفر النموذج.
    """
    global OPENAI_AVAILABLE, client, openai_error_message, openai_last_check

    print("🚨 تهيئة OpenAI: بدء التهيئة...")

    try:
        from openai import OpenAI
        print("🚨 تهيئة OpenAI: تم استيراد الحزمة بنجاح")

        # الحصول على مفتاح API من Config
        api_key = Config.OPENAI_API_KEY
        print(f"🚨 تهيئة OpenAI: مفتاح API = {api_key[:20]}..." if api_key else "🚨 تهيئة OpenAI: مفتاح API = None")
        print(f"🚨 تهيئة OpenAI: وجود مفتاح API: {bool(api_key)}")
        print(f"🚨 تهيئة OpenAI: طول مفتاح API: {len(api_key) if api_key else 0}")

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "لم يتم تكوين مفتاح OpenAI API"
            print(f"🚨 تهيئة OpenAI: ❌ فشل فحص مفتاح API - غير مكون أو لا يزال افتراضي")
            OPENAI_AVAILABLE = False
            return False

        print("🚨 تهيئة OpenAI: إنشاء عميل OpenAI...")
        client = OpenAI(api_key=api_key)
        print("🚨 تهيئة OpenAI: تم إنشاء العميل بنجاح")

        try:
            print("🚨 تهيئة OpenAI: اختبار توفر النموذج...")
            models = client.models.list()
            model_ids = [m.id for m in models.data]
            print(f"🚨 تهيئة OpenAI: تم العثور على {len(model_ids)} نموذج")
            print(f"🚨 تهيئة OpenAI: النماذج الأولى: {model_ids[:5]}")

            if "gpt-4o" not in model_ids:
                openai_error_message = "نموذج GPT-4o غير متوفر في حسابك"
                print(f"🚨 تهيئة OpenAI: ❌ نموذج GPT-4o غير موجود في النماذج المتاحة")
                OPENAI_AVAILABLE = False
                return False

            print("🚨 تهيئة OpenAI: ✅ تم العثور على نموذج GPT-4o!")
            OPENAI_AVAILABLE = True
            openai_error_message = ""
            openai_last_check = time.time()
            print("🚨 تهيئة OpenAI: ✅ تمت التهيئة بنجاح!")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"🚨 تهيئة OpenAI: ❌ خطأ في قائمة النماذج: {error_msg}")
            if "insufficient_quota" in error_msg:
                openai_error_message = "الحساب لا يحتوي على رصيد API. يرجى إضافة أموال إلى حساب OpenAI API الخاص بك."
            elif "invalid_api_key" in error_msg:
                openai_error_message = "مفتاح API غير صالح. يرجى التحقق من متغير البيئة OPENAI_API_KEY."
            elif "rate limit" in error_msg.lower():
                openai_error_message = "تم تجاوز حد المعدل. يرجى المحاولة مرة أخرى لاحقًا."
            else:
                openai_error_message = f"فشل اختبار OpenAI API: {error_msg}"
            OPENAI_AVAILABLE = False
            return False

    except ImportError as e:
        print(f"🚨 تهيئة OpenAI: ❌ خطأ استيراد حزمة OpenAI: {e}")
        openai_error_message = f"حزمة OpenAI غير مثبتة: {e}"
        OPENAI_AVAILABLE = False
        return False
    except Exception as e:
        print(f"🚨 تهيئة OpenAI: ❌ خطأ تهيئة عام: {str(e)}")
        openai_error_message = f"خطأ تهيئة OpenAI: {str(e)}"
        OPENAI_AVAILABLE = False
        return False

def detect_investing_frame(image_str, image_format):
    """
    كشف إطار investing.com المحسن
    """
    try:
        print("🔄 كشف إطار INVESTING: جاري كشف إطار investing.com...")

        system_prompt = """
        أنت محلل مخططات تداول محترف. مهمتك هي الكشف عما إذا كان هذا إطار investing.com وتحديد الإطار الزمني.

        **علامات INVESTING.COM للبحث عنها:**
        - نص "Investing" في أي مكان
        - "powered by TradingView"
        - "NASDAQ", "NYSE", أو أسماء بورصات أخرى
        - أسماء شركات مثل "Tesla", "Apple", إلخ
        - حجم التداول المعروض بتنسيق "1.387M"
        - تخطيط محدد بأزرار اختيار الوقت

        **كشف الإطار الزمني لـ INVESTING.COM:**
        - ابحث عن مؤشرات الإطار الزمني: "15", "30", "1H", "4H", "1D", "1W", "1M"
        - افحص المناطق العلوية حيث توجد أزرار الإطار الزمني عادة
        - "15" تعني عادة M15 (15 دقيقة)
        - "1H" تعني H1 (1 ساعة)
        - "4H" تعني H4 (4 ساعات)

        **تعليمات حاسمة:**
        - إذا رأيت أي علامات investing.com، أعد "investing" كنوع الإطار
        - اكشف الإطار الزمني وأعده بالتنسيق القياسي (M15, H1, H4, إلخ)
        - إذا لم يتم العثور على علامات investing.com، أعد "unknown" كنوع الإطار
        - إذا تعذر تحديد الإطار الزمني، أعد "UNKNOWN" للإطار الزمني
        - **لا تعد رسائل خطأ أو اعتذارات أبدًا**

        تنسيق الإرجاع: "نوع_الإطار,الإطار_الزمني"
        مثال: "investing,M15" أو "unknown,UNKNOWN"
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "حلل صورة المخطط هذه للبحث عن علامات investing.com واكتشف الإطار الزمني. أعد فقط بالتنسيق: 'نوع_الإطار,الإطار_الزمني'"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=50,
            temperature=0.1
        )

        result = response.choices[0].message.content.strip()
        print(f"🔄 نتيجة كشف إطار investing الخام: '{result}'")

        # تحليل النتيجة
        if ',' in result:
            frame_type, timeframe = result.split(',', 1)
            frame_type = frame_type.strip().lower()
            timeframe = timeframe.strip().upper()
            
            # التعامل مع "15" كـ M15 تحديدًا لـ investing.com
            if timeframe == '15':
                timeframe = 'M15'
            
            # التحقق من صحة نوع الإطار
            if frame_type not in ['investing', 'unknown']:
                frame_type = 'unknown'
            
            print(f"🔄 تم التحليل: نوع الإطار: '{frame_type}'، الإطار الزمني: '{timeframe}'")
            return frame_type, timeframe
        else:
            print(f"🔄 ❌ تنسيق غير صالح من كشف إطار investing: '{result}'")
            return "unknown", "UNKNOWN"

    except Exception as e:
        print(f"خطأ: فشل كشف إطار investing: {str(e)}")
        return "unknown", "UNKNOWN"

def detect_currency_from_image(image_str, image_format):
    """
    كشف زوج العملات من صورة المخطط
    """
    try:
        print("🪙 كشف العملة: جاري كشف زوج العملات من الصورة...")

        system_prompt = """
        أنت محلل مخططات تداول محترف. مهمتك هي كشف زوج العملات في صور مخططات التداول.

        **يجب عليك فحص كل هذه المناطق بدقة:**

        **المناطق الرئيسية للفحص:**
        - عنوان/رأس المخطط (الأكثر شيوعًا)
        - الزاوية العلوية اليسرى
        - الزاوية العلوية اليمنى
        - منطقة المركز/الرأس العلوية
        - وسيلة إيضاح أو تسمية المخطط
        - أي نص يعرض أزواج العملات

        **تنسيقات العملات للبحث عنها:**
        - الأزواج الرئيسية: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD
        - الأزواج الثانوية: EUR/GBP, EUR/JPY, GBP/JPY, إلخ
        - العملات الرقمية: BTC/USD, ETH/USD, إلخ
        - الذهب: XAU/USD, GOLD
        - مع أو بدون شرطة مائلة: EURUSD, EUR/USD, GBPUSD, GBP/USD, XAUUSD, XAU/USD
        - أي مجموعة عملات أخرى

        **تعليمات حاسمة:**
        - افحص الصورة بأكملها بشكل منهجي للبحث عن نص زوج العملات
        - ابحث عن النص الذي يبدو أنه زوج عملات (عادة 6-7 أحرف بشرطة مائلة اختيارية)
        - ركز على المناطق التي تظهر عادة اسم الأداة
        - إذا وجدت أي مؤشر لزوج العملات، أعدَه بالتنسيق القياسي (مثل EUR/USD)
        - إذا لم يتم العثور على زوج عملات واضح بعد البحث الشامل، أعد 'UNKNOWN'

        أعد فقط زوج العملات بالتنسيق القياسي (بشرطة مائلة) أو 'UNKNOWN'.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "قم بإجراء بحث شامل عن تسمية زوج العملات في مخطط التداول هذا. افحص جميع المناطق: عنوان المخطط، أعلى اليسار، أعلى اليمين، أعلى المركز، وأي تسميات نصية. أعد فقط زوج العملات مثل EUR/USD, GBP/USD أو UNKNOWN إذا لم يتم العثور بعد البحث الشامل."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100,
            temperature=0.1
        )

        detected_currency = response.choices[0].message.content.strip().upper()
        print(f"🪙 نتيجة كشف العملة الخام: '{detected_currency}'")

        # تنظيف وتوحيد تنسيق العملة
        cleaned_currency = detected_currency.replace(' ', '')
        
        # إضافة شرطة مائلة إذا كانت مفقودة (مثل EURUSD -> EUR/USD)
        if len(cleaned_currency) == 6 and '/' not in cleaned_currency:
            cleaned_currency = f"{cleaned_currency[:3]}/{cleaned_currency[3:]}"
        
        # التعامل مع الذهب تحديدًا
        if 'XAU' in cleaned_currency or 'GOLD' in cleaned_currency:
            cleaned_currency = 'XAU/USD'
        
        print(f"🪙 العملة النظيفة: '{cleaned_currency}'")

        # أزواج العملات الشائعة للتحقق من الصحة
        common_pairs = [
            'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'USD/CAD', 'NZD/USD',
            'EUR/GBP', 'EUR/JPY', 'GBP/JPY', 'EUR/CHF', 'AUD/JPY', 'USD/CNH', 'USD/SGD',
            'BTC/USD', 'ETH/USD', 'XAU/USD', 'XAG/USD'
        ]

        # التحقق مما إذا كان يتطابق مع الأزواج الشائعة
        if cleaned_currency in common_pairs:
            print(f"🪙 ✅ تم كشف زوج عملات صالح: '{cleaned_currency}'")
            return cleaned_currency, None
        elif 'UNKNOWN' in cleaned_currency:
            print(f"🪙 ❌ لم يتم كشف أي زوج عملات")
            return 'UNKNOWN', "لم يتم العثور على زوج العملات في الصورة"
        else:
            print(f"🪙 ⚠️ تم كشف زوج عملات غير شائع: '{cleaned_currency}'")
            return cleaned_currency, None

    except Exception as e:
        print(f"خطأ: فشل كشف العملة: {str(e)}")
        return 'UNKNOWN', f"خطأ في اكتشاف زوج العملات: {str(e)}"

def validate_currency_consistency(first_currency, second_currency):
    """
    التحقق من أن كلا المخططين لنفس زوج العملات
    """
    try:
        print(f"🪙 التحقق من تطابق العملة: الأولى: '{first_currency}'، الثانية: '{second_currency}'")

        if first_currency == 'UNKNOWN' or second_currency == 'UNKNOWN':
            print(f"🪙 ⚠️ تم تخطي التحقق من تطابق العملة - واحدة أو كليهما غير معروفة")
            return True, None  # تخطي التحقق إذا فشل كشف العملة

        # توحيد العملات للمقارنة (إزالة أي مسافات، تحويل لأحرف كبيرة)
        first_normalized = first_currency.replace(' ', '').upper()
        second_normalized = second_currency.replace(' ', '').upper()

        # التحقق مما إذا كانا متماثلين
        if first_normalized == second_normalized:
            print(f"🪙 ✅ نجح التحقق من تطابق العملة")
            return True, None
        else:
            print(f"🪙 ❌ فشل التحقق من تطابق العملة - عملات مختلفة")
            return False, f"❌ العملات مختلفة! الصورة الأولى لـ {first_currency} والصورة الثانية لـ {second_currency}.\n\nيرجى إرسال صور لنفس زوج العملات:\n• الصورة الأولى: M15 لـ {first_currency}\n• الصورة الثانية: H4 لـ {first_currency}"

    except Exception as e:
        print(f"خطأ: فشل التحقق من تطابق العملة: {str(e)}")
        return True, None  # تخطي التحقق عند الخطأ لتجنب حظر المستخدمين

def detect_timeframe_from_image(image_str, image_format):
    """
    كشف الإطار الزمني من صورة المخطط - نسخة محسنة
    """
    try:
        print("🕵️ كشف الإطار الزمني المحسن من الصورة...")

        system_prompt = """
        أنت محلل مخططات تداول محترف. مهمتك الوحيدة هي كشف الإطار الزمني في صور مخططات التداول.

        يجب عليك فحص كل هذه المناطق بدقة:

        **المناطق العلوية:**
        - الزاوية العلوية اليسرى (الأكثر شيوعًا)
        - الزاوية العلوية اليمنى (شائعة جدًا)
        - منطقة المركز/الرأس العلوية
        - شريط عنوان/رأس المخطط

        **المناطق السفلية:**
        - الزاوية السفلية اليسرى
        - الزاوية السفلية اليمنى
        - المركز السفلي أسفل المخطط
        - تسميات المحور السيني (محور الوقت)
        - شريط الحالة أو لوحة المعلومات السفلية

        **مناطق أخرى:**
        - لوحة المقياس/الجانب الأيسر
        - لوحة الجانب الأيمن
        - مربع/تراكب معلومات المخطط
        - أي تسميات نصية في أي مكان في الصورة

        **تنسيقات الإطار الزمني للبحث عنها:**
        - القياسية: M1, M5, M15, M30, H1, H4, D1, W1, MN
        - الاختلافات: 15M, 15m, 1H, 1h, 4H, 4h, 1D, 1d, 1W, 1w
        - كلمات كاملة: 1 Minute, 5 Minutes, 15 Minutes, 30 Minutes, 1 Hour, 4 Hours, Daily, Weekly, Monthly
        - مع تسميات: TF: M15, Timeframe: H4, Period: D1
        - investing.com محددة: "15" (تعني M15), "1H", "4H", إلخ.

        **تعليمات حاسمة:**
        - افحص الصورة بأكملها بشكل منهجي من الأعلى إلى الأسفل، من اليسار إلى اليمين
        - انتبه بشكل خاص للمناطق السفلية التي غالبًا ما يتم تجاهلها
        - ابحث عن النص الصغير في الزوايا والحواف
        - افحص كلا التنسيقين القياسي والاختلافات
        - إذا وجدت أي مؤشر للإطار الزمني، أعدَه
        - إذا لم يتم العثور على إطار زمني واضح بعد البحث الشامل، أعد 'UNKNOWN'

        أعد فقط رمز الإطار الزمني بالتنسيق القياسي أو 'UNKNOWN'.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "قم بإجراء بحث شامل عن تسمية الإطار الزمني في مخطط التداول هذا. افحص جميع المناطق: أعلى اليسار، أعلى اليمين، أعلى المركز، أسفل اليسار، أسفل اليمين، أسفل المركز، المحور السيني، اللواحق الجانبية، وأي تسميات نصية. أعد فقط رمز الإطار الزمني مثل M15, H4, D1 أو UNKNOWN إذا لم يتم العثور بعد البحث الشامل."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100,
            temperature=0.1
        )

        detected_timeframe = response.choices[0].message.content.strip().upper()
        print(f"🕵️ نتيجة كشف الإطار الزمني الخام: '{detected_timeframe}'")

        # تنظيف وتحسين الصحة
        cleaned_timeframe = detected_timeframe.replace(' ', '').replace('TF:', '').replace('TIMEFRAME:', '').replace('PERIOD:', '').replace('TIMEFRAME', '').replace('PERIOD', '')
        print(f"🕵️ الإطار الزمني النظيف: '{cleaned_timeframe}'")

        # خريطة شاملة للإطار الزمني - الترتيب مهم! افحص السلاسل الأطول أولاً
        timeframe_map = {
            # اختلافات M15 - افحص هذه أولاً لتجنب الإيجابيات الخاطئة لـ M1
            '15MINUTES': 'M15', '15MINUTE': 'M15', '15MIN': 'M15', '15M': 'M15', '15m': 'M15', 'M15M': 'M15',
            # حالة خاصة لـ investing.com "15"
            '15': 'M15',
            # اختلافات M30
            '30MINUTES': 'M30', '30MINUTE': 'M30', '30MIN': 'M30', '30M': 'M30', '30m': 'M30', 'M30M': 'M30',
            # اختلافات H4
            '4HOURS': 'H4', '4HOUR': 'H4', '4H': 'H4', '4h': 'H4', 'H4H': 'H4', '240M': 'H4',
            # اختلافات H1
            '1HOUR': 'H1', '1H': 'H1', '1h': 'H1', 'H1H': 'H1', '60M': 'H1', '60MIN': 'H1',
            # اختلافات D1
            'DAILY': 'D1', '1DAY': 'D1', '1D': 'D1', '1d': 'D1', 'D1D': 'D1',
            # اختلافات W1
            'WEEKLY': 'W1', '1WEEK': 'W1', '1W': 'W1', '1w': 'W1',
            # اختلافات MN
            'MONTHLY': 'MN', '1MONTH': 'MN', 'MN': 'MN',
            # اختلافات M5
            '5MINUTES': 'M5', '5MINUTE': 'M5', '5MIN': 'M5', '5M': 'M5', '5m': 'M5', 'M5M': 'M5',
            # اختلافات M1 - افحص هذه الأخيرة لتجنب الإيجابيات الخاطئة
            '1MINUTE': 'M1', '1MIN': 'M1', '1M': 'M1', '1m': 'M1', 'M1M': 'M1'
        }

        # حاول المطابقة التامة أولاً - بالترتيب حسب الأولوية
        for timeframe_variant, standard_tf in timeframe_map.items():
            if cleaned_timeframe == timeframe_variant:
                print(f"🕵️ مطابقة تامة: '{cleaned_timeframe}' -> '{standard_tf}'")
                return standard_tf, None

        # حاول المطابقة الجزئية بالأولوية (الأطر الزمنية الأطول أولاً)
        priority_timeframes = ['M15', 'M30', 'H4', 'H1', 'D1', 'W1', 'MN', 'M5', 'M1']

        for tf in priority_timeframes:
            if tf in cleaned_timeframe:
                print(f"🕵️ مطابقة جزئية: تم العثور على '{tf}' في '{cleaned_timeframe}'")
                return tf, None

        # حالة خاصة: إذا رأينا "15" في أي مكان، أعط الأولوية لـ M15
        if '15' in cleaned_timeframe and any(word in cleaned_timeframe for word in ['M', 'MIN', 'MINUTE']):
            print(f"🕵️ حالة خاصة: تم العثور على '15' في '{cleaned_timeframe}'، إعادة M15")
            return 'M15', None

        # حالة خاصة: إذا رأينا "1" ولكن من المحتمل أن يكون جزءًا من "15"، كن حذرًا
        if '1' in cleaned_timeframe and '15' not in cleaned_timeframe and any(word in cleaned_timeframe for word in ['M', 'MIN', 'MINUTE']):
            # أعد M1 فقط إذا كنا متأكدين أنه ليس M15
            if cleaned_timeframe in ['1M', '1MIN', '1MINUTE', 'M1']:
                print(f"🕵️ كشف M1 الواثق: '{cleaned_timeframe}'")
                return 'M1', None

        # حاول الكشف القائم على الكلمات مع أولوية M15
        if any(word in cleaned_timeframe for word in ['MINUTE', 'MIN', 'M']):
            if '15' in cleaned_timeframe or 'FIFTEEN' in cleaned_timeframe:
                print(f"🕵️ قائم على الكلمات: تم كشف M15 من '{cleaned_timeframe}'")
                return 'M15', None
            elif '30' in cleaned_timeframe or 'THIRTY' in cleaned_timeframe:
                print(f"🕵️ قائم على الكلمات: تم كشف M30 من '{cleaned_timeframe}'")
                return 'M30', None
            elif '5' in cleaned_timeframe or 'FIVE' in cleaned_timeframe:
                print(f"🕵️ قائم على الكلمات: تم كشف M5 من '{cleaned_timeframe}'")
                return 'M5', None
            elif '1' in cleaned_timeframe and '15' not in cleaned_timeframe:
                print(f"🕵️ قائم على الكلمات: تم كشف M1 من '{cleaned_timeframe}'")
                return 'M1', None

        if any(word in cleaned_timeframe for word in ['HOUR', 'H']):
            if '4' in cleaned_timeframe or 'FOUR' in cleaned_timeframe:
                print(f"🕵️ قائم على الكلمات: تم كشف H4 من '{cleaned_timeframe}'")
                return 'H4', None
            elif '1' in cleaned_timeframe:
                print(f"🕵️ قائم على الكلمات: تم كشف H1 من '{cleaned_timeframe}'")
                return 'H1', None

        if any(word in cleaned_timeframe for word in ['DAY', 'D']):
            print(f"🕵️ قائم على الكلمات: تم كشف D1 من '{cleaned_timeframe}'")
            return 'D1', None

        if any(word in cleaned_timeframe for word in ['WEEK', 'W']):
            print(f"🕵️ قائم على الكلمات: تم كشف W1 من '{cleaned_timeframe}'")
            return 'W1', None

        if any(word in cleaned_timeframe for word in ['MONTH', 'MN']):
            print(f"🕵️ قائم على الكلمات: تم كشف MN من '{cleaned_timeframe}'")
            return 'MN', None

        print(f"🕵️ لم يتم العثور على إطار زمني صالح في '{cleaned_timeframe}'، إعادة UNKNOWN")
        return 'UNKNOWN', None

    except Exception as e:
        print(f"خطأ: فشل كشف الإطار الزمني المحسن: {str(e)}")
        return 'UNKNOWN', None

def validate_timeframe_for_analysis(image_str, image_format, expected_timeframe):
    """
    تحقق صارم للتحليل الأول والثاني مع كشف محسن
    """
    try:
        print(f"🕵️ تحقق صارم: نتوقع '{expected_timeframe}'")

        detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)

        if detection_error:
            return False, f"❌ لا يمكن تحليل الإطار الزمني للصورة. يرجى التأكد من أن الصورة تحتوي على إطار {expected_timeframe} واضح."

        print(f"🕵️ نتيجة التحقق: المكتشف '{detected_timeframe}'، المتوقع '{expected_timeframe}'")

        if detected_timeframe == expected_timeframe:
            print(f"🕵️ ✅ نجح التحقق")
            return True, None
        elif detected_timeframe == 'UNKNOWN':
            print(f"🕵️ ❌ فشل التحقق - لم يتم كشف إطار زمني")
            return False, f"❌ لم يتم العثور على إطار زمني واضح في الصورة. يرجى:\n• التأكد من أن الإطار الزمني ({expected_timeframe}) مرئي في الصورة\n• تحميل صورة أوضح تحتوي على {expected_timeframe}\n• التأكد من أن النص غير مقطوع"
        else:
            print(f"🕵️ ❌ فشل التحقق - إطار زمني خاطئ")
            return False, f"❌ الإطار الزمني الموجود في الصورة هو {detected_timeframe} ولكن المطلوب هو {expected_timeframe}.\n\nيرجى تحميل صورة تحتوي على الإطار الزمني الصحيح:\n• للتحليل الأول: M15 (15 دقيقة)\n• للتحليل الثاني: H4 (4 ساعات)"

    except Exception as e:
        print(f"خطأ: فشل التحقق من الإطار الزمني: {str(e)}")
        return False, f"❌ خطأ في التحقق من الإطار الزمني: {str(e)}"

def get_technical_analysis(image_str, image_format, timeframe=None, previous_analysis=None, action_type="chart_analysis", currency_pair=None):
    """
    المكالمة الأولى لـ OpenAI: الحصول على التحليل الفني الشامل فقط
    محدودة بشكل صارم إلى 1024 حرف
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI غير متوفر: {openai_error_message}")

    # التحقق الصارم للتحليل الأول والثاني
    if image_str and action_type in ['first_analysis', 'second_analysis']:
        expected_timeframe = 'M15' if action_type == 'first_analysis' else 'H4'
        is_valid, error_msg = validate_timeframe_for_analysis(image_str, image_format, expected_timeframe)
        if not is_valid:
            return error_msg

    max_tokens = 600  # حد محافظ لـ 1024 حرف

    if action_type == "first_analysis":
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قدم تحليلاً فنياً شاملاً للرسم البياني للإطار الزمني M15.

**المطلوب تحليل فني كامل يتضمن:**

### 📊 التحليل الفني لـ M15
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الحرجة:**
**💧 تحليل السيولة باستخدام SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks) 
- قاتل الجلسات (Session Killers)
- مناطق الاختراق (Breaker Blocks)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز فقط على التحليل الفني
- لا تقدم أي توصيات تداول
- استخدم لغة عربية واضحة ومباشرة
- لا تضف عدد الأحرف في النهاية

العملة: {currency_pair if currency_pair else 'غير معروف'}
"""
    elif action_type == "second_analysis":
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قدم تحليلاً فنياً شاملاً للرسم البياني للإطار الزمني H4.

التحليل السابق (M15): {previous_analysis}

**المطلوب تحليل فني كامل يتضمن:**

### 📊 التحليل الفني لـ H4
**🎯 الدمج بين الإطارين الزمنيين:**
**📊 تحليل فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الاستراتيجية:**
**💧 تحليل السيولة على الإطار الأكبر:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز فقط على التحليل الفني
- لا تقدم أي توصيات تداول
- استخدم لغة عربية واضحة ومباشرة
- لا تضف عدد الأحرف في النهاية

العملة: {currency_pair if currency_pair else 'غير معروف'}
"""
    elif action_type == "final_analysis":
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قدم تحليلاً نهائياً شاملاً يجمع بين التحليلين السابقين.

التحليل الأول (M15): {previous_analysis}
التحليل الثاني (H4): {user_analysis}

**المطلوب تحليل نهائي متكامل يتضمن:**

### 📈 التحليل الشامل
**🎯 الاتجاه العام والهيكل الاستراتيجي:**
**📊 مستويات فيبوناتشي الحرجة:**
**🛡️ الدعم والمقاومة الرئيسية:**
**💧 تحليل السيولة الشامل باستخدام SMC وICT**

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز فقط على التحليل الفني
- لا تقدم أي توصيات تداول
- استخدم لغة عربية واضحة ومباشرة
- لا تضف عدد الأحرف في النهاية

العملة: {currency_pair if currency_pair else 'غير معروف'}
"""
    else:  # single_analysis
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قدم تحليلاً فنياً شاملاً للرسم البياني.

**المطلوب تحليل فني كامل يتضمن:**

### 📊 التحليل الفني لـ {timeframe}
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الحرجة:**
**💧 تحليل السيولة باستخدام SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق الاختراق (Breaker Blocks)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز فقط على التحليل الفني
- لا تقدم أي توصيات تداول
- استخدم لغة عربية واضحة ومباشرة
- لا تضف عدد الأحرف في النهاية

العملة: {currency_pair if currency_pair else 'غير معروف'}
"""

    try:
        print(f"🚨 مكالمة التحليل الفني: بدء تحليل {action_type}")

        if image_str:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system", 
                        "content": "أنت محلل فني محترف. قدم تحليلاً فنياً شاملاً فقط بدون توصيات تداول. التزم بعدم تجاوز 1024 حرف."
                    },
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": analysis_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                        ]
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=30
            )
        else:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system", 
                        "content": "أنت محلل فني محترف. قدم تحليلاً فنياً شاملاً فقط بدون توصيات تداول. التزم بعدم تجاوز 1024 حرف."
                    },
                    {
                        "role": "user", 
                        "content": analysis_prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=20
            )

        analysis = response.choices[0].message.content.strip()

        # التحقق من الطول
        if len(analysis) > 1024:
            print(f"⚠️ التحليل الفني: تجاوز 1024 حرف ({len(analysis)})، جاري الاقتطاع...")
            analysis = analysis[:1021] + "..."

        print(f"✅ التحليل الفني: اكتمل، الطول: {len(analysis)} حرف")
        log_openai_response(f"{action_type}_technical", analysis)
        
        return analysis

    except Exception as e:
        print(f"🚨 التحليل الفني: ❌ فشل: {str(e)}")
        raise RuntimeError(f"فشل التحليل الفني: {str(e)}")

def get_trading_recommendations(technical_analysis, image_str, image_format, timeframe, currency_pair, action_type="chart_analysis"):
    """
    المكالمة الثانية لـ OpenAI: الحصول على توصيات التداول المحددة فقط
    محدودة بشكل صارم إلى 1024 حرف
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI غير متوفر: {openai_error_message}")

    max_tokens = 500  # حد محافظ للتوصيات

    # 🟡 وقف خسارة خاص للذهب مقابل الأزواج الأخرى
    if currency_pair and currency_pair.upper() in ['XAU/USD', 'XAUUSD', 'GOLD']:
        stop_loss_instruction = "الحد الأقصى لوقف الخسارة: 5 نقاط للذهب فقط (تعادل 50 نقطة في العملات)"
        print("🟡 تم كشف الذهب: استخدام قواعد وقف الخسارة الخاصة (5 نقاط)")
    else:
        stop_loss_instruction = "الحد الأقصى لوقف الخسارة: 50 نقطة فقط"
        print("🟢 عملة عادية: استخدام قواعد وقف الخسارة القياسية (50 نقطة)")

    recommendations_prompt = f"""
أنت خبير توصيات تداول محترف. بناءً على التحليل الفني التالي، قدم توصيات تداول عملية واضحة.

التحليل الفني:
{technical_analysis}

**المطلوب توصيات تداول عملية تتضمن:**

### 💼 التوصيات العملية للـ15 دقيقة القادمة
**🎯 التوصية الرئيسية:**
- توصية واضحة (شراء/بيع/انتظار)
- السبب الأساسي

**📊 نقاط التنفيذ:**
- نقطة الدخول الدقيقة
- {stop_loss_instruction}
- أهداف جني الأرباح (هدف أول، هدف ثاني)
- نسبة المخاطرة إلى العائد (1:2 كحد أدنى)

**⏰ التوقيت:**
- الإطار الزمني للتنفيذ: الـ15 دقيقة القادمة
- المدة المتوقعة للصفقة

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز فقط على التوصيات العملية القابلة للتنفيذ
- كن مباشراً وواضحاً
- استخدم لغة عربية واضحة
- لا تضف عدد الأحرف في النهاية
- لا تكرر التحليل الفني

العملة: {currency_pair if currency_pair else 'غير معروف'}
الإطار الزمني: {timeframe}
"""

    try:
        print(f"🚨 مكالمة توصيات التداول: بدء توصيات {action_type}")

        if image_str:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system", 
                        "content": "أنت خبير توصيات تداول. قدم توصيات عملية واضحة وقابلة للتنفيذ خلال 15 دقيقة. التزم بعدم تجاوز 1024 حرف."
                    },
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": recommendations_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                        ]
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=30
            )
        else:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system", 
                        "content": "أنت خبير توصيات تداول. قدم توصيات عملية واضحة وقابلة للتنفيذ خلال 15 دقيقة. التزم بعدم تجاوز 1024 حرف."
                    },
                    {
                        "role": "user", 
                        "content": recommendations_prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=20
            )

        recommendations = response.choices[0].message.content.strip()

        # التحقق من الطول
        if len(recommendations) > 1024:
            print(f"⚠️ التوصيات: تجاوز 1024 حرف ({len(recommendations)})، جاري الاقتطاع...")
            recommendations = recommendations[:1021] + "..."

        print(f"✅ توصيات التداول: اكتملت، الطول: {len(recommendations)} حرف")
        log_openai_response(f"{action_type}_recommendations", recommendations)
        
        return recommendations

    except Exception as e:
        print(f"🚨 توصيات التداول: ❌ فشل: {str(e)}")
        # إرجاع توصيات فارغة بدلاً من الفشل completamente
        return "تعذر توليد التوصيات في الوقت الحالي. يرجى مراجعة التحليل الفني."

def get_user_feedback(user_analysis_text):
    """
    مكالمة واحدة لتقييم تحليل المستخدم (يجمع بين التحليل والتقييم)
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI غير متوفر: {openai_error_message}")

    feedback_prompt = f"""
أنت خبير تحليل فني صارم وصادق. قم بتقييم تحليل المستخدم التالي بصدق وموضوعية.

تحليل المستخدم:
{user_analysis_text}

**تعليمات صارمة:**
1. قيم التحليل بناءً على الدقة الفنية والمنطق
2. كن صادقًا وواضحًا - إذا كان التحليل ضعيفًا أو خاطئًا، قل ذلك بوضوح
3. لا تبالغ في الإيجابيات إذا كانت غير موجودة
4. ركز على الأخطاء الجسيمة في التفكير التحليلي
5. قدم نقدًا بناءً مع حلول عملية

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- كن مباشراً وواضحاً
- ركز على النقاط الأساسية
- لا تضف عدد الأحرف في النهاية
"""

    try:
        print(f"🚨 مكالمة تقييم المستخدم: بدء تقييم تحليل المستخدم")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "أنت خبير تحليل فني صارم. قدم تقييماً صادقاً وموضوعياً لتحليل المستخدم. التزم بعدم تجاوز 1024 حرف."
                },
                {
                    "role": "user", 
                    "content": feedback_prompt
                }
            ],
            max_tokens=600,
            temperature=0.7,
            timeout=20
        )

        feedback = response.choices[0].message.content.strip()

        # التحقق من الطول
        if len(feedback) > 1024:
            print(f"⚠️ تقييم المستخدم: تجاوز 1024 حرف ({len(feedback)})، جاري الاقتطاع...")
            feedback = feedback[:1021] + "..."

        print(f"✅ تقييم المستخدم: اكتمل، الطول: {len(feedback)} حرف")
        
        return feedback, ""  # إرجاع توصيات فارغة لتقييم المستخدم

    except Exception as e:
        print(f"🚨 تقييم المستخدم: ❌ فشل: {str(e)}")
        raise RuntimeError(f"فشل تقييم تحليل المستخدم: {str(e)}")

def load_image_from_url(image_url):
    """تحميل وتشفير الصورة من URL وإرجاع (b64string, format) أو (None, None)"""
    try:
        print(f"🚨 تحميل الصورة: جاري تحميل الصورة من {image_url}")
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            if img.format in ['PNG', 'JPEG', 'JPG']:
                buffered = BytesIO()
                img_format = img.format if img.format else 'JPEG'
                img.save(buffered, format=img_format)
                b64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
                print(f"🚨 تحميل الصورة: ✅ تم تحميل الصورة بنجاح، التنسيق: {img_format}، الحجم: {len(b64_data)} حرف")
                return b64_data, img_format
        print(f"🚨 تحميل الصورة: ❌ فشل تحميل الصورة، الحالة: {response.status_code}")
        return None, None
    except Exception as e:
        print(f"🚨 تحميل الصورة: ❌ خطأ في تحميل الصورة: {e}")
        return None, None

# إزالة وظيفة التقصير نهائياً
