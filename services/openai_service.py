# services/openai_service.py
import time
import base64
import requests
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
    try:
        from openai import OpenAI
        api_key = Config.OPENAI_API_KEY

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "OpenAI API key not configured"
            OPENAI_AVAILABLE = False
            return False

        client = OpenAI(api_key=api_key)

        try:
            models = client.models.list()
            model_ids = [m.id for m in models.data]
            if "gpt-4o" not in model_ids:
                openai_error_message = "GPT-4o model not available in your account"
                OPENAI_AVAILABLE = False
                return False

            OPENAI_AVAILABLE = True
            openai_error_message = ""
            openai_last_check = time.time()
            return True
        except Exception as e:
            error_msg = str(e)
            if "insufficient_quota" in error_msg:
                openai_error_message = "Account has no API credits. Please add funds to your OpenAI API account."
            elif "invalid_api_key" in error_msg:
                openai_error_message = "Invalid API key. Please check your OPENAI_API_KEY environment variable."
            else:
                openai_error_message = f"OpenAI API test failed: {error_msg}"
            OPENAI_AVAILABLE = False
            return False

    except ImportError:
        openai_error_message = "OpenAI package not installed"
        OPENAI_AVAILABLE = False
        return False
    except Exception as e:
        openai_error_message = f"OpenAI initialization error: {str(e)}"
        OPENAI_AVAILABLE = False
        return False

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, user_analysis=None, action_type="chart_analysis"):
    """
    Analyze an image or text using OpenAI and enforce a character limit in responses.
    Mirrors the original analyze logic.
    """
    global client

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

    if image_str:
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

    # backup enforcement of character limit
    if len(analysis) > char_limit + 100:
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

    return analysis

def load_image_from_url(image_url):
    """Load and encode image from URL and return (b64string, format) or (None, None)"""
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            if img.format in ['PNG', 'JPEG', 'JPG']:
                buffered = BytesIO()
                img_format = img.format if img.format else 'JPEG'
                img.save(buffered, format=img_format)
                return base64.b64encode(buffered.getvalue()).decode("utf-8"), img_format
        return None, None
    except Exception as e:
        print(f"Error loading image: {e}")
        return None, None
