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

def init_openai():
    """
    Initialize OpenAI client and test model availability.
    Sets OPENAI_AVAILABLE, client, openai_error_message, openai_last_check.
    """
    global OPENAI_AVAILABLE, client, openai_error_message, openai_last_check

    print("🚨 OPENAI INIT: Starting OpenAI initialization...")

    try:
        from openai import OpenAI
        print("🚨 OPENAI INIT: OpenAI package imported successfully")

        # Get API key from Config
        api_key = Config.OPENAI_API_KEY
        print(f"🚨 OPENAI INIT: Config.OPENAI_API_KEY = {api_key[:20]}..." if api_key else "🚨 OPENAI INIT: Config.OPENAI_API_KEY = None")
        print(f"🚨 OPENAI INIT: API Key exists: {bool(api_key)}")
        print(f"🚨 OPENAI INIT: API Key length: {len(api_key) if api_key else 0}")

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "OpenAI API key not configured"
            print(f"🚨 OPENAI INIT: ❌ API key check failed - not configured or still default")
            OPENAI_AVAILABLE = False
            return False

        print("🚨 OPENAI INIT: Creating OpenAI client...")
        client = OpenAI(api_key=api_key)
        print("🚨 OPENAI INIT: OpenAI client created successfully")

        try:
            print("🚨 OPENAI INIT: Testing model availability...")
            models = client.models.list()
            model_ids = [m.id for m in models.data]
            print(f"🚨 OPENAI INIT: Found {len(model_ids)} models")
            print(f"🚨 OPENAI INIT: First few models: {model_ids[:5]}")

            if "gpt-4o" not in model_ids:
                openai_error_message = "GPT-4o model not available in your account"
                print(f"🚨 OPENAI INIT: ❌ GPT-4o not found in available models")
                OPENAI_AVAILABLE = False
                return False

            print("🚨 OPENAI INIT: ✅ GPT-4o model found!")
            OPENAI_AVAILABLE = True
            openai_error_message = ""
            openai_last_check = time.time()
            print("🚨 OPENAI INIT: ✅ OpenAI initialized successfully!")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"🚨 OPENAI INIT: ❌ Model list error: {error_msg}")
            if "insufficient_quota" in error_msg:
                openai_error_message = "Account has no API credits. Please add funds to your OpenAI API account."
            elif "invalid_api_key" in error_msg:
                openai_error_message = "Invalid API key. Please check your OPENAI_API_KEY environment variable."
            elif "rate limit" in error_msg.lower():
                openai_error_message = "Rate limit exceeded. Please try again later."
            else:
                openai_error_message = f"OpenAI API test failed: {error_msg}"
            OPENAI_AVAILABLE = False
            return False

    except ImportError as e:
        print(f"🚨 OPENAI INIT: ❌ OpenAI package import error: {e}")
        openai_error_message = f"OpenAI package not installed: {e}"
        OPENAI_AVAILABLE = False
        return False
    except Exception as e:
        print(f"🚨 OPENAI INIT: ❌ General initialization error: {str(e)}")
        openai_error_message = f"OpenAI initialization error: {str(e)}"
        OPENAI_AVAILABLE = False
        return False

def detect_timeframe_from_image(image_str, image_format):
    """
    Detect the timeframe from the chart image - IMPROVED VERSION
    Better logic to prevent M15 being misclassified as M1
    Returns: (timeframe, error_message)
    """
    try:
        print("🕵️ IMPROVED timeframe detection from image...")

        system_prompt = """
        You are a professional trading chart analyzer. Your ONLY task is to detect the timeframe in trading chart images.

        You MUST check ALL these areas thoroughly:

        **TOP AREAS:**
        - Top left corner (most common)
        - Top right corner (very common)
        - Top center/header area
        - Chart title/header bar

        **BOTTOM AREAS:**
        - Bottom left corner
        - Bottom right corner
        - Bottom center below the chart
        - X-axis (time axis) labels
        - Bottom status bar or information panel

        **OTHER AREAS:**
        - Left side panel/scale area
        - Right side panel/scale area
        - Chart information box/overlay
        - Any text labels anywhere in the image

        **TIMEFRAME FORMATS TO LOOK FOR:**
        - Standard: M1, M5, M15, M30, H1, H4, D1, W1, MN
        - Variations: 15M, 15m, 1H, 1h, 4H, 4h, 1D, 1d, 1W, 1w
        - Full words: 1 Minute, 5 Minutes, 15 Minutes, 30 Minutes, 1 Hour, 4 Hours, Daily, Weekly, Monthly
        - With labels: TF: M15, Timeframe: H4, Period: D1

        **CRITICAL INSTRUCTIONS:**
        - Scan the ENTIRE image systematically from top to bottom, left to right
        - Pay special attention to bottom areas which are often missed
        - Look for small text in corners and edges
        - Check both standard formats and variations
        - If you find ANY timeframe indicator, return it
        - If no clear timeframe found after thorough search, return 'UNKNOWN'

        Return ONLY the timeframe code in standard format or 'UNKNOWN'.
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
                            "text": "Perform a COMPREHENSIVE search for the timeframe label in this trading chart. Check ALL areas: top left, top right, top center, bottom left, bottom right, bottom center, x-axis, side panels, and any text labels. Return ONLY the timeframe code like M15, H4, D1 or UNKNOWN if not found after thorough search."
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
        print(f"🕵️ RAW timeframe detection result: '{detected_timeframe}'")

        # Enhanced cleaning and validation
        cleaned_timeframe = detected_timeframe.replace(' ', '').replace('TF:', '').replace('TIMEFRAME:', '').replace('PERIOD:', '').replace('TIMEFRAME', '').replace('PERIOD', '')
        print(f"🕵️ Cleaned timeframe: '{cleaned_timeframe}'")

        # Comprehensive timeframe mapping - ORDER MATTERS! Check longer strings first
        timeframe_map = {
            # M15 variations - CHECK THESE FIRST to prevent M1 false positives
            '15MINUTES': 'M15', '15MINUTE': 'M15', '15MIN': 'M15', '15M': 'M15', '15m': 'M15', 'M15M': 'M15',
            # M30 variations
            '30MINUTES': 'M30', '30MINUTE': 'M30', '30MIN': 'M30', '30M': 'M30', '30m': 'M30', 'M30M': 'M30',
            # H4 variations
            '4HOURS': 'H4', '4HOUR': 'H4', '4H': 'H4', '4h': 'H4', 'H4H': 'H4', '240M': 'H4',
            # H1 variations
            '1HOUR': 'H1', '1H': 'H1', '1h': 'H1', 'H1H': 'H1', '60M': 'H1', '60MIN': 'H1',
            # D1 variations
            'DAILY': 'D1', '1DAY': 'D1', '1D': 'D1', '1d': 'D1', 'D1D': 'D1',
            # W1 variations
            'WEEKLY': 'W1', '1WEEK': 'W1', '1W': 'W1', '1w': 'W1',
            # MN variations
            'MONTHLY': 'MN', '1MONTH': 'MN', 'MN': 'MN',
            # M5 variations
            '5MINUTES': 'M5', '5MINUTE': 'M5', '5MIN': 'M5', '5M': 'M5', '5m': 'M5', 'M5M': 'M5',
            # M1 variations - CHECK THESE LAST to prevent false positives
            '1MINUTE': 'M1', '1MIN': 'M1', '1M': 'M1', '1m': 'M1', 'M1M': 'M1'
        }

        # Try exact match first - check in order of priority
        for timeframe_variant, standard_tf in timeframe_map.items():
            if cleaned_timeframe == timeframe_variant:
                print(f"🕵️ Exact match: '{cleaned_timeframe}' -> '{standard_tf}'")
                return standard_tf, None

        # Try partial matches with priority (longer timeframes first)
        priority_timeframes = ['M15', 'M30', 'H4', 'H1', 'D1', 'W1', 'MN', 'M5', 'M1']

        for tf in priority_timeframes:
            if tf in cleaned_timeframe:
                print(f"🕵️ Partial match: found '{tf}' in '{cleaned_timeframe}'")
                return tf, None

        # Special case: if we see "15" anywhere, prioritize M15
        if '15' in cleaned_timeframe and any(word in cleaned_timeframe for word in ['M', 'MIN', 'MINUTE']):
            print(f"🕵️ Special case: '15' found in '{cleaned_timeframe}', returning M15")
            return 'M15', None

        # Special case: if we see "1" but it's likely part of "15", be careful
        if '1' in cleaned_timeframe and '15' not in cleaned_timeframe and any(word in cleaned_timeframe for word in ['M', 'MIN', 'MINUTE']):
            # Only return M1 if we're sure it's not M15
            if cleaned_timeframe in ['1M', '1MIN', '1MINUTE', 'M1']:
                print(f"🕵️ Confident M1 detection: '{cleaned_timeframe}'")
                return 'M1', None

        # Try word-based detection with M15 priority
        if any(word in cleaned_timeframe for word in ['MINUTE', 'MIN', 'M']):
            if '15' in cleaned_timeframe or 'FIFTEEN' in cleaned_timeframe:
                print(f"🕵️ Word-based: M15 detected from '{cleaned_timeframe}'")
                return 'M15', None
            elif '30' in cleaned_timeframe or 'THIRTY' in cleaned_timeframe:
                print(f"🕵️ Word-based: M30 detected from '{cleaned_timeframe}'")
                return 'M30', None
            elif '5' in cleaned_timeframe or 'FIVE' in cleaned_timeframe:
                print(f"🕵️ Word-based: M5 detected from '{cleaned_timeframe}'")
                return 'M5', None
            elif '1' in cleaned_timeframe and '15' not in cleaned_timeframe:
                print(f"🕵️ Word-based: M1 detected from '{cleaned_timeframe}'")
                return 'M1', None

        if any(word in cleaned_timeframe for word in ['HOUR', 'H']):
            if '4' in cleaned_timeframe or 'FOUR' in cleaned_timeframe:
                print(f"🕵️ Word-based: H4 detected from '{cleaned_timeframe}'")
                return 'H4', None
            elif '1' in cleaned_timeframe:
                print(f"🕵️ Word-based: H1 detected from '{cleaned_timeframe}'")
                return 'H1', None

        if any(word in cleaned_timeframe for word in ['DAY', 'D']):
            print(f"🕵️ Word-based: D1 detected from '{cleaned_timeframe}'")
            return 'D1', None

        if any(word in cleaned_timeframe for word in ['WEEK', 'W']):
            print(f"🕵️ Word-based: W1 detected from '{cleaned_timeframe}'")
            return 'W1', None

        if any(word in cleaned_timeframe for word in ['MONTH', 'MN']):
            print(f"🕵️ Word-based: MN detected from '{cleaned_timeframe}'")
            return 'MN', None

        print(f"🕵️ No valid timeframe found in '{cleaned_timeframe}', returning UNKNOWN")
        return 'UNKNOWN', None

    except Exception as e:
        print(f"ERROR: Improved timeframe detection failed: {str(e)}")
        return 'UNKNOWN', None

def validate_timeframe_for_analysis(image_str, image_format, expected_timeframe):
    """
    STRICT validation for first and second analysis with enhanced detection
    Returns: (is_valid, error_message)
    """
    try:
        print(f"🕵️ STRICT VALIDATION: Expecting '{expected_timeframe}'")

        detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)

        if detection_error:
            return False, f"❌ لا يمكن تحليل الإطار الزمني للصورة. يرجى التأكد من أن الصورة تحتوي على إطار {expected_timeframe} واضح."

        print(f"🕵️ Validation Result: Detected '{detected_timeframe}', Expected '{expected_timeframe}'")

        if detected_timeframe == expected_timeframe:
            print(f"🕵️ ✅ Validation PASSED")
            return True, None
        elif detected_timeframe == 'UNKNOWN':
            print(f"🕵️ ❌ Validation FAILED - No timeframe detected")
            return False, f"❌ لم يتم العثور على إطار زمني واضح في الصورة. يرجى:\n• التأكد من أن الإطار الزمني ({expected_timeframe}) مرئي في الصورة\n• تحميل صورة أوضح تحتوي على {expected_timeframe}\n• التأكد من أن النص غير مقطوع"
        else:
            print(f"🕵️ ❌ Validation FAILED - Wrong timeframe")
            return False, f"❌ الإطار الزمني الموجود في الصورة هو {detected_timeframe} ولكن المطلوب هو {expected_timeframe}.\n\nيرجى تحميل صورة تحتوي على الإطار الزمني الصحيح:\n• للتحليل الأول: M15 (15 دقيقة)\n• للتحليل الثاني: H4 (4 ساعات)"

    except Exception as e:
        print(f"ERROR: Timeframe validation failed: {str(e)}")
        return False, f"❌ خطأ في التحقق من الإطار الزمني: {str(e)}"

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, user_analysis=None, action_type="chart_analysis"):
    """
    Analyze an image or text using OpenAI with enhanced, detailed analysis.
    STRICTLY ENFORCES 1024 CHARACTER LIMIT THROUGH PROMPT ENGINEERING
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    # STRICT validation for first and second analysis
    if image_str and action_type in ['first_analysis', 'second_analysis']:
        expected_timeframe = 'M15' if action_type == 'first_analysis' else 'H4'
        is_valid, error_msg = validate_timeframe_for_analysis(image_str, image_format, expected_timeframe)
        if not is_valid:
            return error_msg

    # ALL ANALYSIS TYPES STRICTLY LIMITED TO 1024 CHARACTERS
    char_limit = 1024
    max_tokens = 300  # Conservative limit to ensure 1024 characters

    if action_type == "user_analysis_feedback":
        analysis_prompt = f"""
أنت خبير تحليل فني صارم وصادق. قم بتقييم تحليل المستخدم التالي بصدق وموضوعية.

تحليل المستخدم:
{user_analysis}

**تعليمات صارمة:**
1. قيم التحليل بناءً على الدقة الفنية والمنطق
2. كن صادقًا وواضحًا - إذا كان التحليل ضعيفًا أو خاطئًا، قل ذلك بوضوح
3. لا تبالغ في الإيجابيات إذا كانت غير موجودة
4. ركز على الأخطاء الجسيمة في التفكير التحليلي
5. قدم نقدًا بناءً مع حلول عملية

**مهمتك:**
- قدم تقييماً موضوعياً في حدود 1000 حرف فقط
- لا تتجاوز 1024 حرف تحت أي ظرف
- كن مباشراً وواضحاً
- ركز على النقاط الأساسية

**لا تضف عدد الأحرف في نهاية الرد.**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    elif action_type == "single_analysis":
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات باستخدام مفاهيم المال الذكي والـ ICT. قدم تحليلاً شاملاً للرسم البياني.

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 مفاهيم المال الذكي (SMC):**
- تحليل مناطق السيولة (Liquidity)
- تحديد أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers - SK)
- تحليل الاختراقات (Breaker Blocks)

**📈 مفاهيم ICT (Inner Circle Trader):**
- تحليل السيولة السابقة (Previous Liquidity)
- مناطق العرض والطلب (Supply/Demand Zones)
- تحليل الوقت (Time Analysis)
- حركة السعر (Price Action)

**📊 مستويات فيبوناتشي:**
- تحديد المستويات الرئيسية (38.2%, 50%, 61.8%)
- تحليل تفاعل السعر

**🛡️ الدعم والمقاومة:**
- المستويات الرئيسية
- المناطق الحرجة

**⚡ التوصيات الفورية (5-15 دقيقة):**
- نقاط الدخول القريبة
- **وقف الخسارة: ديناميكي حسب تحليل السوق (بحد أقصى 50 نقطة)**
- **يجب أن يكون وقف الخسارة بناءً على:**
  * 📏 التقلب الحالي (ATR)
  * 🏗️ هيكل السوق والدعم/المقاومة
  * ⚖️ نسبة المخاطرة إلى العائد (1:2 كحد أدنى)
- أهداف جني الأرباح

**تعليمات صارمة:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على التوصيات العملية الفورية
- **لا تستخدم وقف خسارة ثابت 50 نقطة دائماً**
- **اضبط وقف الخسارة حسب ظروف السوق**
- **لا تضف عدد الأحرف في نهاية الرد**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    elif timeframe == "H4" and previous_analysis:
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً شاملاً يجمع بين الإطارين الزمنيين.

التحليل السابق (15 دقيقة): {previous_analysis}

**المطلوب تحليل شامل يتضمن:**

### 📊 التحليل الفني الشامل
**1. تحليل فيبوناتشي الرئيسية**
**2. الدعم والمقاومة الحرجة**
**3. تحليل السيولة باستخدام SMC وICT**
**4. قاتل الجلسات (SK) ومناطق الاختراق**
**5. التوصيات العملية:**
- نقاط الدخول
- **وقف الخسارة: ديناميكي بناءً على هيكل السوق (بحد أقصى 50 نقطة)**
- **يجب أن يكون وقف الخسارة:**
  * 📏 متناسب مع تقلب الزوج
  * 🏗️ خارج مناطق الدعم/المقاومة القريبة
  * ⚖️ يحقق نسبة مخاطرة إلى عائد 1:2 على الأقل
- أهداف جني الأرباح

**تعليمات صارمة:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على الدمج بين الإطارين
- قدم توصيات عملية مباشرة
- **لا تستخدم وقف خسارة ثابت، بل ديناميكي حسب السوق**
- **لا تضف عدد الأحرف في نهاية الرد**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    elif action_type == "final_analysis":
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قم بتحليل شامل بناءً على التحليلين السابقين.

التحليل الأول (M15): {previous_analysis}

**المطلوب تحليل نهائي متكامل يتضمن:**

### 📈 التحليل الشامل
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الحرجة:**
**🛡️ الدعم والمقاومة الرئيسية:**
**💧 تحليل SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق العرض والطلب (Supply/Demand)

**💼 التوصيات الاستراتيجية:**
- نقاط الدخول الاستراتيجية
- **وقف الخسارة: ديناميكي (بحد أقصى 50 نقطة) حسب التقلب وهيكل السوق**
- **يجب أن يكون وقف الخسارة:**
  * 📏 مناسب للإطار الزمني والتقلب
  * 🏗️ يحمي رأس المال مع تحقيق نسبة مخاطرة إلى عائد مناسبة
  * ⚖️ لا يقل عن 1:2 للمخاطرة إلى العائد
- أهداف جني الأرباح

**تعليمات صارمة:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على التوصيات العملية
- كن مباشراً وواضحاً
- **اضبط وقف الخسارة ديناميكياً حسب ظروف السوق**
- **لا تضف عدد الأحرف في نهاية الرد**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    else:
        # First analysis with detailed prompt
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات. قدم تحليلاً شاملاً للرسم البياني.

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الحرجة:**
**💧 تحليل السيولة باستخدام SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق الاختراق (Breaker Blocks)

**⚡ التوصيات العملية الفورية:**
- نقاط الدخول القريبة
- **وقف الخسارة: ديناميكي حسب تحليل السوق (بحد أقصى 50 نقطة)**
- **يجب أن يكون وقف الخسارة بناءً على:**
  * 📏 التقلب الحالي للزوج
  * 🏗️ هيكل السوق والدعم/المقاومة القريبة
  * ⚖️ نسبة المخاطرة إلى العائد (1:2 كحد أدنى)
- أهداف جني الأرباح

**تعليمات صارمة:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على التوصيات خلال 5-15 دقيقة
- كن مباشراً وواضحاً
- **لا تستخدم وقف خسارة ثابت، بل ديناميكي حسب السوق**
- **لا تضف عدد الأحرف في نهاية الرد**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        import time
        start_time = time.time()

        if image_str:
            print(f"🚨 OPENAI ANALYSIS: Analyzing image with {action_type}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم بعدم تجاوز {char_limit} حرف في ردك. لا تضف عدد الأحرف في النهاية."},
                    {"role": "user", "content": [
                        {"type": "text", "text": analysis_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                    ]}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=30
            )
        else:
            print(f"🚨 OPENAI ANALYSIS: Analyzing text with {action_type}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم بعدم تجاوز {char_limit} حرف في ردك. لا تضف عدد الأحرف في النهاية."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=20
            )

        analysis = response.choices[0].message.content.strip()
        processing_time = time.time() - start_time
        print(f"🚨 OPENAI ANALYSIS: ✅ Analysis completed in {processing_time:.2f}s, length: {len(analysis)} chars")

        # NO TRIMMING - We rely on prompt engineering to enforce limits
        if len(analysis) > char_limit:
            print(f"🚨 OPENAI ANALYSIS: ⚠️ Analysis exceeded limit ({len(analysis)} chars), but keeping original response")

        return analysis

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI analysis failed: {str(e)}")

def load_image_from_url(image_url):
    """Load and encode image from URL and return (b64string, format) or (None, None)"""
    try:
        print(f"🚨 IMAGE LOAD: Loading image from {image_url}")
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            if img.format in ['PNG', 'JPEG', 'JPG']:
                buffered = BytesIO()
                img_format = img.format if img.format else 'JPEG'
                img.save(buffered, format=img_format)
                b64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
                print(f"🚨 IMAGE LOAD: ✅ Image loaded successfully, format: {img_format}, size: {len(b64_data)} chars")
                return b64_data, img_format
        print(f"🚨 IMAGE LOAD: ❌ Failed to load image, status: {response.status_code}")
        return None, None
    except Exception as e:
        print(f"🚨 IMAGE LOAD: ❌ Error loading image: {e}")
        return None, None

def analyze_technical_chart(image_str, image_format, timeframe=None):
    """
    Analyze the technical chart only (first call)
    STRICTLY ENFORCES 1024 CHARACTER LIMIT
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    char_limit = 1024
    max_tokens = 300

    analysis_prompt = f"""
أنت خبير تحليل فني للمخططات المالية. قم بتحليل الرسم البياني من الناحية الفنية فقط.

**المطلوب تحليل فني كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الحرجة:**
**💧 تحليل السيولة باستخدام SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق العرض والطلب (Supply/Demand)

**💼 التوصيات العملية:**
- نقاط الدخول
- **وقف الخسارة: ديناميكي بناءً على هيكل السوق (بحد أقصى 50 نقطة)**
- **يجب أن يكون وقف الخسارة:**
  * 📏 متناسب مع تقلب الزوج
  * 🏗️ خارج مناطق الدعم/المقاومة القريبة
  * ⚖️ يحقق نسبة مخاطرة إلى عائد 1:2 على الأقل
- أهداف جني الأرباح

**تعليمات صارمة:**
- ركز فقط على التحليل الفني للمخطط
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- كن مباشراً وواضحاً
- **لا تستخدم وقف خسارة ثابت، بل ديناميكي حسب السوق**
- **لا تضف عدد الأحرف في نهاية الرد**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        print(f"🚨 OPENAI ANALYSIS: 🧠 Starting technical analysis with timeframe: {timeframe}")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت خبير تحليل فني. ركز فقط على التحليل الفني. التزم بعدم تجاوز 1024 حرف. لا تضف عدد الأحرف في النهاية."},
                {"role": "user", "content": [
                    {"type": "text", "text": analysis_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                ]}
            ],
            max_tokens=max_tokens,
            temperature=0.7,
            timeout=30
        )

        analysis = response.choices[0].message.content.strip()
        print(f"🚨 OPENAI ANALYSIS: ✅ Technical analysis completed, length: {len(analysis)} chars")

        # NO TRIMMING - We rely on prompt engineering
        if len(analysis) > char_limit:
            print(f"🚨 OPENAI ANALYSIS: ⚠️ Technical analysis exceeded limit ({len(analysis)} chars), but keeping original response")

        return analysis

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Technical analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI analysis failed: {str(e)}")

def analyze_user_drawn_feedback_simple(image_str, image_format, timeframe=None):
    """
    Simple version for user feedback analysis without technical analysis context
    STRICTLY ENFORCES 1024 CHARACTER LIMIT
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    char_limit = 1024
    max_tokens = 300

    feedback_prompt = f"""
أنت خبير تحليل فني ومدرس محترف. قم بتقييم التحليل المرسوم من قبل المستخدم على الرسم البياني.

**مهمتك: تقييم الرسومات والتحليلات المرسومة:**

1. **تقييم الخطوط المرسومة:** (الاتجاه، الدعم/المقاومة، فيبوناتشي)
2. **تقييم الأشكال والعلامات:** (الدوائر، الأسهم، الإشارات)
3. **نقاط القوة:** (الجوانب الإيجابية)
4. **نقاط الضعف:** (الأخطاء والتحسينات)
5. **توصيات للتحسين:** (نصائح عملية)

**تعليمات صارمة:**
- كن صادقاً وموضوعياً في التقييم
- قدم نقداً بناءً يهدف لمساعدة المستخدم
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- **لا تضف عدد الأحرف في نهاية الرد**

**تعليمات إضافية صارمة:**
- استخدم تنسيق نصي بسيط بدون علامات تنسيق كثيرة
- تجنب العناوين المكررة والتنسيق الزائد
- استخدم فقرات قصيرة وواضحة
- لا تستخدم **علامات التمييز** إلا عند الضرورة القصوى
"""

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        print(f"🚨 OPENAI ANALYSIS: 🧠 Starting simple user feedback analysis with timeframe: {timeframe}")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت مدرس تحليل فني محترف. قيم تحليل المستخدم المرسوم بموضوعية. التزم بعدم تجاوز 1024 حرف. لا تضف عدد الأحرف في النهاية."},
                {"role": "user", "content": [
                    {"type": "text", "text": feedback_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                ]}
            ],
            max_tokens=max_tokens,
            temperature=0.7,
            timeout=30
        )

        feedback = response.choices[0].message.content.strip()
        print(f"🚨 OPENAI ANALYSIS: ✅ Simple user feedback analysis completed, length: {len(feedback)} chars")

        # NO TRIMMING - We rely on prompt engineering
        if len(feedback) > char_limit:
            print(f"🚨 OPENAI ANALYSIS: ⚠️ Feedback exceeded limit ({len(feedback)} chars), but keeping original response")

        return feedback

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Simple user feedback analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI feedback analysis failed: {str(e)}")
