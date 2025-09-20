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

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

analysis_sessions = {}

OPENAI_AVAILABLE = False
client = None
openai_error_message = ""
openai_last_check = 0

def init_openai():
    global OPENAI_AVAILABLE, client, openai_error_message, openai_last_check

    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "OpenAI API key not configured"
            return False

        client = OpenAI(api_key=api_key)

        try:
            models = client.models.list()
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

init_openai()

def is_complete_response(response_text):
    if not response_text or len(response_text.strip()) < 150:
        return False
    
    last_char = response_text.strip()[-1]
    if last_char not in ['.', '!', '?', ':', ';', '،', ')', ']', '}']:
        return False
    
    incomplete_patterns = [
        r'\(Stop-L', r'\(Take-P', r'\(SL', r'\(TP', 
        r'إيقاف الخسارة', r'وقف الخسارة', r'أخذ الربح',
        r'...', r'…', r'\.\.\.'
    ]
    
    for pattern in incomplete_patterns:
        if re.search(pattern, response_text[-20:]):
            return False
    
    key_sections = ['الاتجاه', 'الدعم', 'المقاومة', 'الدخول', 'الخروج', 'المخاطر']
    found_sections = sum(1 for section in key_sections if section in response_text)
    
    return found_sections >= 4

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None):
    if timeframe == "H4" and previous_analysis:
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً واضحاً وشاملاً للشارت المعروض للإطار 4 ساعات.

بناءً على التحليل السابق للإطار 15 دقيقة:
{previous_analysis}

ركز على النقاط التالية في تحليلك:
1. تحليل الاتجاه العام وهيكل السوق
2. تحديد مستويات الدعم والمقاومة الرئيسية
3. تحليل مؤشر RSI والمتوسطات المتحركة
4. تحديد مناطق الدخول والخروج المحتملة
5. إدارة المخاطر ونسب المكافأة إلى المخاطرة

**ملاحظة مهمة**: يجب أن يكون تحليلك مكتملاً ولا ينقطع فجأة. تأكد من إنهاء جميع الجمل بشكل صحيح.
"""
    else:
        analysis_prompt = """
أنت محلل فني محترف. قدم تحليلاً واضحاً وشاملاً للشارت المعروض للإطار 15 دقيقة.

ركز على النقاط التالية في تحليلك:
1. تحليل الاتجاه العام وهيكل السوق
2. تحديد مستويات الدعم والمقاومة الرئيسية
3. تحليل مؤشر RSI إذا كان مرئياً
4. تحديد مناطق الدخول والخروج المحتملة
5. إدارة المخاطر الأساسية

**ملاحظة مهمة**: يجب أن يكون تحليلك مكتملاً ولا ينقطع فجأة. تأكد من إنهاء جميع الجمل بشكل صحيح.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "أنت محلل فني محترف. قدم تحليلاً دقيقاً وعملياً بلغة واضحة. تأكد من إكمال جميع أقسام التحليل وعدم قطع الرد فجأة. ركز على الجوانب العملية للتداول."
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
        max_tokens=3000,
        temperature=0.7
    )

    return response.choices[0].message.content.strip()

@app.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

@app.route('/multi-timeframe-analyze', methods=['POST'])
def multi_timeframe_analyze():
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

        if user_id not in analysis_sessions:
            analysis_sessions[user_id] = {
                'm15_analysis': None,
                'h4_analysis': None,
                'created_at': datetime.now(),
                'status': 'awaiting_m15'
            }

        session = analysis_sessions[user_id]

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

        buffered = BytesIO()
        img_format = img.format if img.format else 'JPEG'
        img.save(buffered, format=img_format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        if session['status'] == 'awaiting_m15' or not timeframe:
            analysis = analyze_with_openai(img_str, img_format, "M15")
            
            if not is_complete_response(analysis):
                incomplete_sections = []
                if 'المخاطر' not in analysis or 'إيقاف الخسارة' not in analysis:
                    incomplete_sections.append("إدارة المخاطر")
                if 'الدخول' not in analysis or 'الخروج' not in analysis:
                    incomplete_sections.append("نقاط الدخول والخروج")
                
                if incomplete_sections:
                    completion_note = f"\n\n⚠️ ملاحظة: التحليل غير مكتمل في قسم {', '.join(incomplete_sections)}. يوصى بمراجعة هذه النقاط يدوياً."
                    analysis += completion_note
                
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
            analysis = analyze_with_openai(img_str, img_format, "H4", session['m15_analysis'])
            
            if not is_complete_response(analysis):
                incomplete_sections = []
                if 'المخاطر' not in analysis or 'إيقاف الخسارة' not in analysis:
                    incomplete_sections.append("إدارة المخاطر")
                if 'الدخول' not in analysis or 'الخروج' not in analysis:
                    incomplete_sections.append("نقاط الدخول والخروج")
                
                if incomplete_sections:
                    completion_note = f"\n\n⚠️ ملاحظة: التحليل غير مكتمل في قسم {', '.join(incomplete_sections)}. يوصى بمراجعة هذه النقاط يدوياً."
                    analysis += completion_note
                
            session['h4_analysis'] = analysis
            session['status'] = 'completed'

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

@app.route('/sendpulse-analyze', methods=['POST'])
def sendpulse_analyze():
    return multi_timeframe_analyze()

@app.route('/status')
def status():
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
