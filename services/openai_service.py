# services/openai_service.py
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

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, user_analysis=None, action_type="chart_analysis"):
    """
    Analyze an image or text using OpenAI and enforce a character limit in responses.
    Mirrors the original analyze logic.
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    if action_type == "user_analysis_feedback":
        char_limit = 800
        analysis_prompt = f"""
أنت خبير تحليل فني. قم بتقييم تحليل المستخدم التالي وتقديم ملاحظات بناءة:

تحليل المستخدم:
{user_analysis}

**التزم الصارم بالشروط التالية:**
1. لا تتجاوز {char_limit} حرف تحت أي ظرف
2. قدم نقاط قوة التحليل
3. قدم نقاط تحسين مع شرح موجز
4. قدم نصيحة عملية واحدة

**تأكد من عد الأحرف والالتزام بالحد {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    elif timeframe == "H4" and previous_analysis:
        char_limit = 800
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً نهائياً موجزاً جداً يجمع بين الإطارين.

التحليل السابق (15 دقيقة): {previous_analysis[:150]}...

**التزم الصارم بالشروط التالية:**
1. لا تتجاوز {char_limit} حرف تحت أي ظرف
2. دمج الرؤيات من الإطارين
3. تقديم توصية تداول واحدة واضحة
4. ذكر إدارة المخاطرة باختصار

**المطلوب في 3 نقاط فقط:**
1. الصورة الكلية من الإطارين
2. التوصية الاستراتيجية
3. إدارة المخاطرة

**تأكد من عد الأحرف والالتزام بالحد {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    else:
        char_limit = 600
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً دقيقاً ومختصراً للغاية للشارت.

**التزم الصارم بالشروط التالية:**
1. لا تتجاوز {char_limit} حرف تحت أي ظرف
2. ركز على النقاط العملية فقط
3. استخدم لغة مختصرة جداً

**المطلوب في 4 نقاط فقط:**
1. الاتجاه العام (سطر واحد)
2. أهم مستوى دعم ومقاومة (سطر واحد)
3. توصية تداول واضحة (سطر واحد)
4. إدارة المخاطرة (سطر واحد)

**تأكد من عد الأحرف والالتزام بالحد {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        if image_str:
            print(f"🚨 OPENAI ANALYSIS: Analyzing image with {action_type}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم الصارم بعدم تجاوز {char_limit} حرف في ردك."},
                    {"role": "user", "content": [
                        {"type": "text", "text": analysis_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "high"}}
                    ]}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )
        else:
            print(f"🚨 OPENAI ANALYSIS: Analyzing text with {action_type}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم الصارم بعدم تجاوز {char_limit} حرف في ردك."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )

        analysis = response.choices[0].message.content.strip()
        print(f"🚨 OPENAI ANALYSIS: ✅ Analysis completed, length: {len(analysis)} chars")

        # backup enforcement of character limit
        if len(analysis) > char_limit + 100:
            print(f"🚨 OPENAI ANALYSIS: Analysis too long ({len(analysis)}), retrying with shorter version")
            retry_prompt = f"""
التحليل السابق كان طويلاً جداً ({len(analysis)} حرف). أعد كتابته مع الالتزام بعدم تجاوز {char_limit} حرف:

{analysis}
"""
            retry_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"اختصار النص إلى {char_limit} حرف."},
                    {"role": "user", "content": retry_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7
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
