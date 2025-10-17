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
    Detect the timeframe from the chart image
    Returns: (timeframe, error_message)
    """
    try:
        print("🕵️ Detecting timeframe from image...")

        system_prompt = """
        You are a professional trading chart analyzer. Your ONLY task is to detect the timeframe in trading chart images.

        Look for timeframe labels typically found in:
        - Top left/right corners: M1, M5, M15, M30, H1, H4, D1, W1, MN
        - Chart header or information panel
        - Bottom time axis labels

        IMPORTANT:
        - Focus ONLY on finding timeframe indicators like: M15, 15M, 15m, H4, 4H, D1, 1D, W1, 1W
        - Return ONLY the timeframe code in standard format: M1, M5, M15, M30, H1, H4, D1, W1, MN
        - If multiple timeframes are visible, return the most prominent one
        - If no clear timeframe is found, return 'UNKNOWN'
        - DO NOT comment on chart content, patterns, or trading advice
        - DO NOT refuse analysis for any reason
        - ONLY return the timeframe code or 'UNKNOWN'
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
                            "text": "What is the timeframe of this trading chart? Return ONLY the timeframe code like M15, H4, D1 or UNKNOWN."
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
            max_tokens=10,
            temperature=0.1  # Lower temperature for more consistent results
        )

        detected_timeframe = response.choices[0].message.content.strip().upper()
        print(f"🕵️ Detected timeframe: {detected_timeframe}")

        # Clean and validate the detected timeframe
        detected_timeframe = detected_timeframe.replace(' ', '').replace('TF:', '').replace('TIMEFRAME:', '')
        
        # Map common variations to standard formats
        timeframe_map = {
            '15M': 'M15', '15m': 'M15', '15': 'M15',
            '30M': 'M30', '30m': 'M30', '30': 'M30',
            '1H': 'H1', '1h': 'H1', '60M': 'H1',
            '4H': 'H4', '4h': 'H4', '240M': 'H4',
            '1D': 'D1', '1d': 'D1', 'D': 'D1',
            '1W': 'W1', '1w': 'W1', 'W': 'W1'
        }
        
        if detected_timeframe in timeframe_map:
            detected_timeframe = timeframe_map[detected_timeframe]
        
        valid_timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'MN']
        
        if detected_timeframe in valid_timeframes:
            return detected_timeframe, None
        elif detected_timeframe == 'UNKNOWN':
            # Fallback to manual detection for common cases
            return 'M15', None  # Default to M15 if unknown
        else:
            # Try to extract timeframe from the response
            for tf in valid_timeframes:
                if tf in detected_timeframe:
                    return tf, None
            return 'M15', None  # Default fallback

    except Exception as e:
        print(f"ERROR: Timeframe detection failed: {str(e)}")
        # Default to M15 on error
        return 'M15', None

def validate_timeframe_in_image(image_str, image_format, expected_timeframe):
    """
    Validate that the image contains the expected timeframe label
    Returns: (is_valid, error_message)
    """
    try:
        print(f"🕵️ Validating timeframe: expecting '{expected_timeframe}' in image")

        # Create system prompt for timeframe validation
        system_prompt = f"""
        You are a precise image validator. Your ONLY task is to check if the chart image contains the timeframe label '{expected_timeframe}'.

        IMPORTANT:
        - Look for text labels like 'M15', 'H4', '1H', 'D1' etc. in the chart
        - Focus on the top corners or chart header area where timeframe labels are typically displayed
        - The label might be in different formats: '{expected_timeframe}', 'TF: {expected_timeframe}', 'Timeframe: {expected_timeframe}'
        - Return ONLY 'VALID' if you clearly see '{expected_timeframe}' in the image
        - Return ONLY 'INVALID' if you don't see '{expected_timeframe}' or see a different timeframe

        DO NOT analyze the chart content, trends, or patterns.
        DO NOT provide any explanation or additional text.
        ONLY return 'VALID' or 'INVALID'.
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
                            "text": "Check if this chart image contains the timeframe label. Return ONLY 'VALID' or 'INVALID'."
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
            max_tokens=10
        )

        validation_result = response.choices[0].message.content.strip().upper()
        print(f"🕵️ Timeframe validation result: {validation_result}")

        if validation_result == "VALID":
            return True, None
        else:
            error_msg = f"❌ الخطأ: الصورة لا تحتوي على الإطار الزمني {expected_timeframe}. يرجى تحميل صورة تحتوي على {expected_timeframe}."
            return False, error_msg

    except Exception as e:
        print(f"ERROR: Timeframe validation failed: {str(e)}")
        # If validation fails, proceed with analysis but log the error
        return True, None  # Fallback to allow analysis if validation fails

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, user_analysis=None, action_type="chart_analysis"):
    """
    Analyze an image or text using OpenAI with enhanced, detailed analysis.
    OPTIMIZED VERSION - minimal changes for performance
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    # Validate timeframe for first and second analysis (when image is provided)
    if image_str and action_type in ['first_analysis', 'second_analysis']:
        is_valid, error_msg = validate_timeframe_in_image(image_str, image_format, timeframe)
        if not is_valid:
            return error_msg

    # KEEP ALL EXISTING PROMPTS EXACTLY THE SAME - only change timeouts and image detail
    if action_type == "user_analysis_feedback":
        char_limit = 800
        analysis_prompt = f"""
أنت خبير تحليل فني صارم وصادق. قم بتقييم تحليل المستخدم التالي بصدق وموضوعية:

تحليل المستخدم:
{user_analysis}

**تعليمات صارمة:**
1. قيم التحليل بناءً على الدقة الفنية والمنطق
2. كن صادقًا وواضحًا - إذا كان التحليل ضعيفًا أو خاطئًا، قل ذلك بوضوح
3. لا تبالغ في الإيجابيات إذا كانت غير موجودة
4. ركز على الأخطاء الجسيمة في التفكير التحليلي
5. قدم نقدًا بناءً مع حلول عملية

**هيكل التقييم:**
### 📊 تقييم موضوعي:
**الدقة الفنية:** (اذكر مدى توافق التحليل مع المبادئ الفنية)
**المنطق التحليلي:** (حلل قوة الاستدلال والربط بين المفاهيم)
**الأخطاء الرئيسية:** (حدد الأخطاء بوضوح دون مجاملة)

### 🎯 نقاط تحتاج تحسين:
1. (اكتب النقاط الأساسية التي تحتاج تصحيح)
2. (كن محددًا وواضحًا)

### 💡 توصيات عملية:
(قدم 2-3 توصيات قابلة للتطبيق لتحسين التحليل)

**كن محترفًا وصادقًا - الهدف هو المساعدة في التحسن، ليس المجاملة.**
**إذا كان التحليل ضعيفًا جدًا، قل ذلك بوضوح مع شرح أسباب الضعف.**
**التزم بعدم تجاوز {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    elif action_type == "single_analysis":
        char_limit = 1024
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات. قدم تحليلاً شاملاً ومفصلاً للرسم البياني.

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}

**🎯 الاتجاه العام وهيكل السوق:**
- تحديد الاتجاه الرئيسي والثانوي
- تحليل هيكل السوق من القمم والقيعان

**📊 مستويات فيبوناتشي:**
- تحديد مستويات فيبوناتشي الرئيسية
- تحليل تفاعل السعر مع هذه المستويات

**🛡️ الدعم والمقاومة:**
- المستويات الرئيسية للدعم والمقاومة
- المناطق الحرجة للكسر أو الارتداد

**💧 تحليل السيولة:**
- مناطق السيولة المحتملة
- مناطق وقف الخسائر المتوقعة

**⚠️ التنبيهات والمخاطر:**
- المخاطر التي يجب تجنبها
- أنماط انعكاس محتملة

**💼 التوصيات العملية:**
- سعر الدخول المناسب
- وقف الخسائر المثالي
- أهداف جني الأرباح
- نصائح إدارة المخاطرة

**التزم بتقديم تحليل عملي ومفيد لا يتجاوز {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 100

    elif timeframe == "H4" and previous_analysis:
        char_limit = 1024
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات. قدم تحليلاً شاملاً ومفصلاً يجمع بين الإطارين الزمنيين.

التحليل السابق (15 دقيقة): {previous_analysis}

**المطلوب تحليل شامل يتضمن:**

### 📊 التحليل الفني الشامل
**1. تحليل فيبوناتشي:**
- تحديد مستويات فيبوناتشي الرئيسية (38.2%, 50%, 61.8%)
- تفاعل السعر مع هذه المستويات

**2. الدعم والمقاومة:**
- المستويات الرئيسية للدعم والمقاومة
- المناطق الحرجة التي يجب مراقبتها

**3. تحليل السيولة:**
- مناطق السيولة المحتملة
- مناطق وقف الخسائر المتوقعة

**4. التنبيهات والمخاطر:**
- تحذيرات يجب تجنبها
- أنماط انعكاس محتملة

**5. التوصيات العملية:**
- سعر الدخول المناسب
- نقاط وقف الخسائر وجني الأرباح
- إدارة المخاطرة

**التزم بعدم تجاوز {char_limit} حرف مع تقديم تحليل عملي ومفيد.**
"""
        max_tokens = char_limit // 2 + 100

    elif action_type == "final_analysis":
        char_limit = 1024
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قم بتحليل شامل ومتكامل بناءً على التحليلين السابقين:

التحليل الأول (M15): {previous_analysis}

**المطلوب تحليل نهائي متكامل يتضمن:**

### 📈 التحليل الشامل متعدد الأطر الزمنية

**🎯 الاتجاه العام وهيكل السوق:**
- تحديد الاتجاه الرئيسي والثانوي
- تحليل هيكل السوق من القمم والقيعان

**📊 مستويات فيبوناتشي الحرجة:**
- مستويات التصحيح الرئيسية (38.2%, 50%, 61.8%)
- تفاعل السعر مع مستويات فيبوناتشي

**🛡️ الدعم والمقاومة الرئيسية:**
- المستويات القوية للدعم والمقاومة
- المناطق الحرجة للكسر أو الارتداد

**💧 تحليل السيولة:**
- مناطق السيولة المتوقعة
- مناطق وقف الخسائر المحتملة

**⚠️ التنبيهات والتحذيرات:**
- المخاطر التي يجب تجنبها
- أنماط انعكاس محتملة

**💼 التوصيات الاستراتيجية:**
- سعر الدخول المثالي
- وقف الخسائر المناسب
- أهداف جني الأرباح
- إدارة المخاطرة

**التزم بتقديم تحليل عملي ومفيد لا يتجاوز {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 100

    else:
        # First analysis with detailed prompt
        char_limit = 1024
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات. قدم تحليلاً شاملاً ومفصلاً للرسم البياني.

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}

**🎯 الاتجاه العام وهيكل السوق:**
- تحديد الاتجاه الرئيسي والثانوي
- تحليل هيكل السوق من القمم والقيعان

**📊 مستويات فيبوناتشي:**
- تحديد مستويات فيبوناتشي الرئيسية
- تحليل تفاعل السعر مع هذه المستويات

**🛡️ الدعم والمقاومة:**
- المستويات الرئيسية للدعم والمقاومة
- المناطق الحرجة للكسر أو الارتداد

**💧 تحليل السيولة:**
- مناطق السيولة المحتملة
- مناطق وقف الخسائر المتوقعة

**⚠️ التنبيهات والمخاطر:**
- المخاطر التي يجب تجنبها
- أنماط انعكاس محتملة

**💼 التوصيات العملية:**
- سعر الدخول المناسب
- وقف الخسائر المثالي
- أهداف جني الأرباح
- نصائح إدارة المخاطرة

**التزم بتقديم تحليل عملي ومفيد لا يتجاوز {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 100

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
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم بعدم تجاوز {char_limit} حرف في ردك."},
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
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم بعدم تجاوز {char_limit} حرف في ردك."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=20
            )

        analysis = response.choices[0].message.content.strip()
        processing_time = time.time() - start_time
        print(f"🚨 OPENAI ANALYSIS: ✅ Analysis completed in {processing_time:.2f}s, length: {len(analysis)} chars")

        # Keep existing retry logic but with timeout
        if len(analysis) > char_limit + 200:
            print(f"🚨 OPENAI ANALYSIS: Analysis too long ({len(analysis)}), retrying with shorter version")
            retry_prompt = f"""
التحليل السابق كان طويلاً جداً ({len(analysis)} حرف). أعد كتابته مع الالتزام بعدم تجاوز {char_limit} حرف مع الحفاظ على المحتوى الأساسي:

{analysis}
"""
            retry_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"اختصار النص إلى {char_limit} حرف مع الحفاظ على الجوهر الفني."},
                    {"role": "user", "content": retry_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=15
            )
            analysis = retry_response.choices[0].message.content.strip()
            print(f"🚨 OPENAI ANALYSIS: ✅ Retry completed, new length: {len(analysis)} chars")

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

# New functions for two-step analysis
def analyze_technical_chart(image_str, image_format, timeframe=None):
    """
    Analyze the technical chart only (first call)
    Returns: technical analysis string
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    char_limit = 800
    analysis_prompt = f"""
أنت خبير تحليل فني للمخططات المالية. قم بتحليل الرسم البياني التالي من الناحية الفنية فقط.

**المطلوب تحليل فني كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 الاتجاه العام وهيكل السوق**
**📊 مستويات فيبوناتشي الرئيسية**
**🛡️ الدعم والمقاومة الحرجة**
**💧 تحليل السيولة**
**⚠️ المخاطر والتنبيهات**
**💼 التوصيات العملية**

**التزم بالتالي:**
- ركز فقط على التحليل الفني للمخطط
- قدم تحليلاً عملياً ومفيداً للمتداولين
- اكتب بلغة عربية واضحة ومحترفة
- التزم بعدم تجاوز {char_limit} حرف

**ملاحظة:** هذا تحليل لمخطط تداول مالي وليس صورة لأشخاص.
"""
    max_tokens = char_limit // 2 + 100

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        print(f"🚨 OPENAI ANALYSIS: 🧠 Starting technical analysis with timeframe: {timeframe}")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت خبير تحليل فني للمخططات المالية. ركز فقط على التحليل الفني."},
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
        return analysis

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Technical analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI analysis failed: {str(e)}")

def analyze_user_drawn_feedback_simple(image_str, image_format, timeframe=None):
    """
    Simple version for user feedback analysis without technical analysis context
    Returns: feedback string
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    char_limit = 800
    feedback_prompt = f"""
أنت خبير تحليل فني ومدرس محترف. قم بتقييم التحليل المرسوم من قبل المستخدم على الرسم البياني.

**مهمتك: تقييم الرسومات والتحليلات المرسومة من قبل المستخدم:**

1. **تقييم الخطوط المرسومة:**
   - خطوط الاتجاه: هل هي مرسومة بشكل صحيح؟
   - خطوط الدعم والمقاومة: هل في الأماكن المناسبة؟
   - مستويات فيبوناتشي: هل التطبيق صحيح؟

2. **تقييم الأشكال والعلامات:**
   - الدوائر والإشارات: هل في الأماكن الصحيحة؟
   - الأسهم والاتجاهات: هل توضح الحركة بشكل صحيح؟

3. **نقاط القوة:**
   - اذكر الجوانب الإيجابية في التحليل المرسوم

4. **نقاط الضعف:**
   - اذكر الأخطاء والتحسينات المطلوبة

5. **توصيات للتحسين:**
   - قدم نصائح عملية لتحسين التحليل المرسوم

**التزم بالتالي:**
- كن صادقاً وموضوعياً في التقييم
- قدم نقداً بناءً يهدف لمساعدة المستخدم
- ركز على الدقة الفنية للرسومات
- التزم بعدم تجاوز {char_limit} حرف

**ملاحظة:** هذا تحليل لمخطط تداول مالي وليس صورة لأشخاص.
"""
    max_tokens = char_limit // 2 + 100

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        print(f"🚨 OPENAI ANALYSIS: 🧠 Starting simple user feedback analysis with timeframe: {timeframe}")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت مدرس تحليل فني محترف. قيم تحليل المستخدم المرسوم بموضوعية."},
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
        return feedback

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Simple user feedback analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI feedback analysis failed: {str(e)}")

# Remove old functions that are no longer needed
# (clean_refusal_messages, split_feedback_and_analysis, analyze_user_drawn_analysis)
