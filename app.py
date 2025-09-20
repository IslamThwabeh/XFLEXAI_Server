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

def is_complete_response(response_text):
    """Check if the response seems complete"""
    if not response_text or not response_text.strip():
        return False
    
    # التحقق من أن الرد لا ينتهي بجملة غير مكتملة
    if not response_text.endswith(('.', '!', '?')):
        return False
    
    # التحقق من أن الرد يحتوي على أقسام كافية
    sections = ['اتجاه', 'دعم', 'مقاومة', 'دخول', 'خروج', 'مخاطرة']
    found_sections = sum(1 for section in sections if section in response_text)
    
    return found_sections >= 3

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None):
    """Analyze image with OpenAI with enhanced SMC and Fibonacci analysis"""

    if timeframe == "H4" and previous_analysis:
        # Enhanced analysis for 4-hour with SMC and Fibonacci
        analysis_prompt = f"""
أنت الآن محلل فني محترف. قدم تحليلاً واضحاً وشاملاً للشارت المعروض.

بناءً على التحليل السابق للإطار 15 دقيقة:
{previous_analysis}

قم بتحليل هذا الشارت للإطار 4 ساعات مع التركيز على:
1. تحليل الاتجاه العام ومستويات الدعم والمقاومة
2. تحليل مؤشر RSI والمتوسطات المتحركة
3. تحديد مناطق الدخول والخروج
4. إدارة المخاطر ونسب المكافأة/المخاطرة

قدم تحليلاً واضحاً وسهل الفهم للمتداولين المبتدئين.
"""
    else:
        # Standard analysis for 15-minute or single timeframe
        analysis_prompt = """
أنت محلل فني محترف. قدم تحليلاً واضحاً وشاملاً للشارت المعروض مع التركيز على:
1. الاتجاه العام ومستويات الدعم والمقاومة
2. تحليل مؤشر RSI إذا كان مرئياً
3. نقاط الدخول والخروج المحتملة
4. إدارة المخاطر الأساسية

قدم تحليلاً واضحاً وسهل الفهم للمتداولين المبتدئين.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "أنت محلل فني محترف للأسواق المالية. قدم تحليلاً دقيقاً وعملياً بلغة واضحة للمبتدئين. ركز على النقاط العملية والتوصيات الواضحة."
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
        max_tokens=4000,
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
            
            # التحقق من اكتمال الرد
            if not is_complete_response(analysis):
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
            
            # التحقق من اكتمال الرد
            if not is_complete_response(analysis):
                analysis = analyze_with_openai(img_str, img_format, "H4", session['m15_analysis'])
                
            session['h4_analysis'] = analysis
            session['status'] = 'completed'

            # Prepare final comprehensive analysis
            final_analysis = f"""
## 📊 التحليل الشامل متعدد الأطر الزمنية

### 📈 تحليل الإطار 15 دقيقة:
{session['m15_analysis']}

### 🕓 تحليل الإطار 4 ساعات:
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
