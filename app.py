import os
import base64
import re
import requests
import json
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import time
from datetime import datetime, timedelta

# تهيئة Flask
app = Flask(__name__)

# تحديد حجم أقصى للرفع (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# تخزين مؤقت للتحليلات (في production استخدم Redis أو قاعدة بيانات)
analysis_sessions = {}

# تهيئة OpenAI Client
OPENAI_AVAILABLE = False
client = None
openai_error_message = ""
openai_last_check = 0

def init_openai():
    """Initialize OpenAI client with error handling"""
    global OPENAI_AVAILABLE, client, openai_error_message, openai_last_check

    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "OpenAI API key not configured"
            return False

        client = OpenAI(api_key=api_key)

        # Test the API with a simple request
        try:
            models = client.models.list()
            # Check if gpt-4o is available
            model_ids = [model.id for model in models.data]
            if "gpt-4o" not in model_ids:
                openai_error_message = "GPT-4o model not available in your account"
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
            return False

    except ImportError:
        openai_error_message = "OpenAI package not installed"
        return False
    except Exception as e:
        openai_error_message = f"OpenAI initialization error: {str(e)}"
        return False

# Initialize OpenAI on startup
init_openai()

def is_valid_analysis(analysis_text):
    """Check if the analysis is valid and not a refusal"""
    refusal_phrases = [
        "sorry", "عذرًا", "لا أستطيع", "cannot", "can't help",
        "I'm sorry", "I am sorry", "unable to", "لا يمكنني"
    ]

    # If the analysis is too short or contains refusal phrases, it's invalid
    if len(analysis_text.strip()) < 50:
        return False

    for phrase in refusal_phrases:
        if phrase.lower() in analysis_text.lower():
            return False

    return True

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None):
    """Analyze image with OpenAI with enhanced SMC and Fibonacci analysis"""

    if timeframe == "H4" and previous_analysis:
        # Enhanced analysis for 4-hour with SMC and Fibonacci
        analysis_prompt = f"""
بناءً على التحليل السابق للإطار 15 دقيقة:
{previous_analysis}

أنت الآن محلل فني محترف متخصص في تحليل الشارتات باستخدام Smart Money Concepts (SMC) ومستويات فيبوناتشي.

قم بتحليل هذا الشارت للإطار 4 ساعات باستخدام القوالب التالية:

### التحليل باستخدام Smart Money Concepts (SMC)
1. **Order Blocks (OB)**:
   - حدد مناطق الطلب (Buying/Selling Zones)
   - حدد أي Order Blocks واضحة على الشارت

2. **Breaker Blocks (BB)**:
   - ابحث عن Breaker Blocks التي قد تشير إلى انعكاسات محتملة

3. **Liquidity Zones**:
   - حدد مناطق السيولة (Liquidity Pools)
   - ابحث عن أي Equal Highs/Lows

4. **Market Structure Shifts (MSS)**:
   - ابحث عن أي تغييرات في هيكل السوق
   - حدد أي Break of Structure (BOS) أو Change of Character (CHoCH)

### التحليل باستخدام مستويات فيبوناتشي
1. **Fibonacci Retracement**:
   - حدد أهم مستويات فيبوناتشي (0.236, 0.382, 0.5, 0.618, 0.786)
   - حدد أي مستويات تعمل كمقاومة أو دعم

2. **Fibonacci Extensions**:
   - ابحث عن مستويات الامتداد (1.272, 1.414, 1.618)
   - حدد أهداف محتملة للحركة السعرية

### التكامل بين الإطارين
1. **التوافق بين الإطارين**:
   - هل هناك توافق بين اتجاه الإطار 15 دقيقة و4 ساعات؟
   - ما هي مستويات الدعم والمقاومة المشتركة؟

2. **التوصيات الاستراتيجية**:
   - نقاط الدخول المثلى بناءً على تحليل SMC وفيبوناتشي
   - تحديد Stop Loss وTake Profit المناسب
   - إدارة المخاطر بناءً على تحليل متعدد الأطر الزمنية

### الخلاصة الاستراتيجية
قدم توصية تداول شاملة بناءً على تحليل:
- متعدد الأطر الزمنية (15 دقيقة + 4 ساعات)
- Smart Money Concepts
- مستويات فيبوناتشي
- إدارة المخاطر المناسبة

⚠️ ملاحظات مهمة:
- ركز على مناطق الدخول عالية الاحتمالية
- حدد مستويات المخاطرة والمكافأة بوضوح
- استخدم لغة احترافية واضحة
"""
    else:
        # Standard analysis for 15-minute or single timeframe
        analysis_prompt = """
أنت محلل فني محترف متخصص في تحليل charts التداول من MT4 و TradingView.
استخدم القالب التالي حصراً لتحليلك:

### الإطار الزمني
حدد الإطار الزمني للchart إذا كان واضحاً.

### النماذج الفنية
ابحث عن أي نماذج فنية مثل:
- نماذج الشموع اليابانية (Engulfing, Hammer, Doji)
- نماذج Chart patterns (Head and Shoulders, Triangles, Flags)

### المؤشرات الفنية
حاول تحديد أي مؤشرات فنية مرئية مثل:
- RSI ومستويات التشبع الشرائي/البيعي
- Moving Averages وتقاطعاتها
- MACD وإشاراته

### مستويات الدعم والمقاومة
حدد مستويات الدعم والمقاومة الرئيسية.

### الاتجاه العام
حدد الاتجاه العام للسوق.

### استراتيجية التداول المحتملة
قدم اقتراحات عملية للتداول.

### ملاحظات عامة
أي ملاحظات إضافية أو تحذيرات مهمة.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "أنت محلل فني محترف للأسواق المالية متخصص في SMC وفيبوناتشي. قدم تحليل دقيق وعملي."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": analysis_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_format.lower()};base64,{image_str}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        max_tokens=2500,
        temperature=0.7
    )

    return response.choices[0].message.content.strip()

@app.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

# New endpoint for multi-timeframe analysis
@app.route('/multi-timeframe-analyze', methods=['POST'])
def multi_timeframe_analyze():
    """
    Handle multi-timeframe analysis with session management
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "message": "لم يتم إرسال بيانات",
                "analysis": "فشل في التحليل: لم يتم إرسال بيانات"
            }), 400

        user_id = data.get('user_id', 'default_user')
        image_url = data.get('last_message') or data.get('image_url')
        timeframe = data.get('timeframe')

        if not image_url:
            return jsonify({
                "message": "لم يتم تقديم رابط الصورة",
                "analysis": "فشل في التحليل: لم يتم تقديم رابط الصورة"
            }), 400

        # Initialize user session if not exists
        if user_id not in analysis_sessions:
            analysis_sessions[user_id] = {
                'm15_analysis': None,
                'h4_analysis': None,
                'created_at': datetime.now(),
                'status': 'awaiting_m15'
            }

        session = analysis_sessions[user_id]

        # Download and process image
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            return jsonify({
                "message": "تعذر تحميل الصورة",
                "analysis": "فشل في التحليل: تعذر تحميل الصورة"
            }), 400

        img = Image.open(BytesIO(response.content))

        if img.format not in ['PNG', 'JPEG', 'JPG']:
            return jsonify({
                "message": "نوع الملف غير مدعوم",
                "analysis": "فشل في التحليل: نوع الملف غير مدعوم"
            }), 400

        if not OPENAI_AVAILABLE:
            return jsonify({
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": f"فشل في التحليل: {openai_error_message}"
            }), 503

        # Convert image to base64
        buffered = BytesIO()
        img_format = img.format if img.format else 'JPEG'
        img.save(buffered, format=img_format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Determine which analysis to perform
        if session['status'] == 'awaiting_m15' or not timeframe:
            # First image - assume M15
            analysis = analyze_with_openai(img_str, img_format, "M15")
            session['m15_analysis'] = analysis
            session['status'] = 'awaiting_h4'

            return jsonify({
                "message": "✅ تم تحليل الشارت 15 دقيقة بنجاح",
                "analysis": analysis,
                "next_step": "الرجاء إرسال صورة الإطار 4 ساعات للتحليل المتكامل",
                "status": "awaiting_h4",
                "user_id": user_id
            }), 200

        elif session['status'] == 'awaiting_h4' and timeframe == "H4":
            # Second image - H4 with comprehensive analysis
            analysis = analyze_with_openai(img_str, img_format, "H4", session['m15_analysis'])
            session['h4_analysis'] = analysis
            session['status'] = 'completed'

            # Prepare final comprehensive analysis
            final_analysis = f"""
## 📊 التحليل الشامل متعدد الأطر الزمنية

### 📈 تحليل الإطار 15 دقيقة:
{session['m15_analysis']}

### 🕓 تحليل الإطار 4 ساعات (مع SMC وفيبوناتشي):
{analysis}

### 🎯 التوصية الاستراتيجية النهائية:
بناءً على التحليل المتكامل للإطارين، يتم تقديم التوصيات التالية:
- نقاط الدخول المثلى
- إدارة المخاطرة المناسبة
- أهداف الربح المحتملة
"""

            # Clean up session after completion
            del analysis_sessions[user_id]

            return jsonify({
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "status": "completed"
            }), 200

        else:
            return jsonify({
                "message": "خطأ في تسلسل التحليل",
                "analysis": "الرجاء البدء بإرسال صورة الإطار 15 دقيقة أولاً"
            }), 400

    except Exception as e:
        return jsonify({
            "message": f"خطأ أثناء المعالجة: {str(e)}",
            "analysis": f"فشل في التحليل: {str(e)}"
        }), 400

# Keep the original endpoint for backward compatibility
@app.route('/sendpulse-analyze', methods=['POST'])
def sendpulse_analyze():
    """
    Backward compatibility endpoint - redirects to multi-timeframe analysis
    """
    return multi_timeframe_analyze()

@app.route('/status')
def status():
    """Endpoint to check API status"""
    if time.time() - openai_last_check > 300:
        init_openai()

    return jsonify({
        "server": "running",
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message,
        "active_sessions": len(analysis_sessions),
        "timestamp": time.time()
    })

@app.route('/clear-sessions')
def clear_sessions():
    """Clear all analysis sessions (for debugging)"""
    global analysis_sessions
    count = len(analysis_sessions)
    analysis_sessions = {}
    return jsonify({
        "message": f"تم مسح {count} جلسة",
        "status": "sessions_cleared"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
