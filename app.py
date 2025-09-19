import os
import base64
import re
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import time

# تهيئة Flask
app = Flask(__name__)

# تحديد حجم أقصى للرفع (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

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

@app.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

@app.route('/status')
def status():
    """Endpoint to check API status"""
    # Re-check OpenAI status if it's been more than 5 minutes
    if time.time() - openai_last_check > 300:
        init_openai()
    
    return jsonify({
        "server": "running",
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message,
        "timestamp": time.time()
    })

@app.route('/reinit-openai')
def reinit_openai():
    """Force reinitialize OpenAI client"""
    success = init_openai()
    return jsonify({
        "success": success,
        "message": "OpenAI client reinitialized",
        "openai_available": OPENAI_AVAILABLE,
        "error": openai_error_message
    })

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

# API لتحليل الصور
@app.route('/analyze', methods=['POST'])
def analyze_image():
    if 'file' not in request.files:
        return jsonify({"error": "لم يتم إرسال صورة. الرجاء إرسال صورة واضحة"}), 400

    file = request.files['file']

    try:
        # التحقق من أن الملف صورة
        img = Image.open(file.stream)
        if img.format not in ['PNG', 'JPEG', 'JPG']:
            return jsonify({"error": "نوع الملف غير مدعوم. الرجاء إرسال PNG أو JPEG"}), 400

        # Re-check OpenAI status if it's been a while
        if time.time() - openai_last_check > 300:
            init_openai()

        # إذا كان OpenAI غير متاح
        if not OPENAI_AVAILABLE:
            return jsonify({
                "error": "خدمة التحليل غير متاحة حالياً",
                "message": "✅ الصورة صالحة ولكن خدمة الذكاء الاصطناعي غير متوفرة",
                "details": openai_error_message,
                "solution": "يرجى التحقق من إعدادات OpenAI API الخاصة بك"
            }), 503

        # تحويل الصورة إلى Base64
        buffered = BytesIO()
        img.save(buffered, format=img.format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Improved prompt for better analysis
        analysis_prompt = """
أنت محلل فني محترف متخصص في تحليل charts التداول من MT4 و TradingView.
مهمتك هي تحليل ANY chart يتم إرساله إليك، بغض النظر عن جودته أو وضوحه.
حتى إذا كان Chart غير واضح أو غير مثالي، قم ببذل قصارى جهدك لتقديم أفضل تحليل ممكن.

استخدم القالب التالي حصراً لتحليلك:

### الإطار الزمني
حدد الإطار الزمني للchart إذا كان واضحاً، وإلا فاذكر أن الإطار غير واضح.

### النماذج الفنية
ابحث عن أي نماذج فنية مثل:
- نماذج الشموع اليابانية (مثل Engulfing, Hammer, Doji)
- نماذج Chart patterns (مثل Head and Shoulders, Triangles, Flags)
- إذا لم تتمكن من تحديد نماذج واضحة، فاذكر ذلك

### المؤشرات الفنية
حاول تحديد أي مؤشرات فنية مرئية مثل:
- RSI ومستويات التشبع الشرائي/البيعي
- Moving Averages وتقاطعاتها
- MACD وإشاراته
- أي مؤشرات أخرى يمكنك تحديدها

### مستويات الدعم والمقاومة
حدد مستويات الدعم والمقاومة الرئيسية بناءً على:
- القمم والقيعان السابقة
- المناطق ذات حجم التداول المرتفع
- أي مستويات نفسية مهمة (مثل الأرقام الدائرية)

### الاتجاه العام
حدد الاتجاه العام للسوق بناءً على:
- اتجاه حركة السعر
- موقع السعر relative إلى المتوسطات المتحركة
- أي إشارات أخرى يمكنك ملاحظتها

### استراتيجية التداول المحتملة
قدم اقتراحات عملية للتداول بناءً على تحليلك:
- نقاط الدخول المحتملة
- نقاط وقف الخسارة المناسبة
- أهداف الربح المحتملة
- إدارة المخاطر المناسبة

### ملاحظات عامة
أي ملاحظات إضافية أو تحذيرات مهمة:
- جودة البيانات ووضوح Chart
- أي قيود في التحليل
- توصيات عامة للتداول

⚠️ ملاحظات مهمة:
- يجب أن يكون التحليل عملياً وقابلاً للتطبيق
- أعطِ قيم رقمية واضحة عندما يكون ذلك ممكناً
- استخدم لغة تقريرية احترافية ومختصرة
- لا ترفض تحليل أي chart لأي سبب كان
- حتى إذا كان Chart غير مثالي، قدم أفضل تحليل ممكن
"""

        # إرسال إلى OpenAI لتحليل فني مضبوط
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "أنت محلل فني محترف للأسواق المالية. مهمتك هي تحليل ANY chart تداول يتم إرساله إليك وتقديم تحليل مفيد وقابل للتطبيق. لا ترفض تحليل أي chart لأي سبب."
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
                                "url": f"data:image/{img.format.lower()};base64,{img_str}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.7  # Slightly higher temperature for more creative analysis
        )

        # استخراج التحليل من الرد
        analysis = response.choices[0].message.content.strip()

        # Check if the analysis is valid
        if not is_valid_analysis(analysis):
            return jsonify({
                "error": "فشل في تحليل الصورة",
                "message": "لم يتمكن الذكاء الاصطناعي من تحليل الصورة بشكل صحيح",
                "details": "التحليل الذي تم إرجاعه غير كافٍ أو يحتوي على عبارات رفض",
                "analysis": analysis  # Still return the analysis for debugging
            }), 400

        return jsonify({"message": "✅ تم تحليل الشارت بنجاح", "analysis": analysis}), 200

    except Exception as e:
        error_msg = str(e)
        
        # Handle specific OpenAI errors
        if "insufficient_quota" in error_msg:
            # Update our status
            init_openai()
            return jsonify({
                "error": "نفذ رصيد خدمة OpenAI",
                "message": "حساب OpenAI لا يحتوي على رصيد كافي.",
                "details": "على الرغم من إضافة الرصيد، قد تحتاج إلى الانتظار قليلاً حتى يصبح الرصيد فعالاً، أو التحقق من أن المفتاح المستخدم مرتبط بالحساب الصحيح.",
                "solution": "الذهاب إلى platform.openai.com والتحقق من الرصيد ونشاط API"
            }), 402
        elif "invalid_api_key" in error_msg:
            init_openai()
            return jsonify({
                "error": "مفتاح API غير صالح",
                "message": "مفتاح API الموجود في البيئة غير صالح أو منتهي الصلاحية."
            }), 401
        elif "rate_limit" in error_msg:
            return jsonify({
                "error": "تم تجاوز الحد المسموح",
                "message": "تم تجاوز الحد المسموح للطلبات. يرجى المحاولة مرة أخرى بعد بضع دقائق."
            }), 429
        else:
            return jsonify({
                "error": "خطأ أثناء معالجة الصورة",
                "message": f"تفاصيل الخطأ: {error_msg}"
            }), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
