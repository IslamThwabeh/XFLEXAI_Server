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

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None):
    """تحليل الصورة مع إجبار OpenAI على الالتزام بعدد أحرف محدد"""
    
    # تحديد الحد الأقصى للأحرف بناءً على نوع التحليل
    if timeframe == "H4" and previous_analysis:
        char_limit = 800  # للتحليل النهائي
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً دقيقاً ومختصراً للغاية للشارت (4 ساعات).

التحليل السابق (15 دقيقة): {previous_analysis[:150]}...

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
    else:
        char_limit = 600  # للتحليل الأولي
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً دقيقاً ومختصراً للغاية للشارت (15 دقيقة).

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

    # حساب الـ tokens المناسبة بناءً على الحد الأقصى للأحرف
    # في المتوسط، كل token عربي ≈ 2-3 حروف، لذا نأخذ هامشاً آمناً
    max_tokens = char_limit // 2 + 50  # هامش إضافي

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": f"أنت محلل فني محترف. التزم الصارم بعدم تجاوز {char_limit} حرف في ردك. استخدم لغة مختصرة جداً وركز على الجوهر."
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
        max_tokens=max_tokens,  # تحديد صارم لـ tokens
        temperature=0.7
    )

    analysis = response.choices[0].message.content.strip()
    
    # التحقق من التزام OpenAI بالحد (للأمان فقط)
    if len(analysis) > char_limit + 100:  # هامش خطأ 100 حرف
        # إذا تجاوز الحد بشكل كبير، نطلب إعادة تحليل مختصر
        retry_prompt = f"""
التحليل السابق كان طويلاً جداً ({len(analysis)} حرف). أعد كتابة التحليل التالي مع الالتزام بعدم تجاوز {char_limit} حرف:

{analysis}

**المطلوب:**
- اختصر التحليل إلى {char_limit} حرف كحد أقصى
- احذف أي معلومات غير ضرورية
- ركز على الجوهر فقط
"""
        
        retry_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"اختصار النص إلى {char_limit} حرف كحد أقصى مع الحفاظ على المعنى."
                },
                {
                    "role": "user",
                    "content": retry_prompt
                }
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        analysis = retry_response.choices[0].message.content.strip()
    
    return analysis

@app.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

@app.route('/multi-timeframe-analyze', methods=['POST'])
def multi_timeframe_analyze():
    try:
        if not request.is_json:
            return jsonify({
                "message": "نوع المحتوى غير مدعوم",
                "analysis": "فشل في التحليل: يجب أن يكون الطلب بتنسيق JSON"
            }), 415

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

        # تهيئة الجلسة
        if user_id not in analysis_sessions:
            analysis_sessions[user_id] = {
                'm15_analysis': None,
                'h4_analysis': None,
                'created_at': datetime.now(),
                'status': 'awaiting_first_image'
            }

        session = analysis_sessions[user_id]

        # تحميل ومعالجة الصورة
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

        # تحويل الصورة إلى base64
        buffered = BytesIO()
        img_format = img.format if img.format else 'JPEG'
        img.save(buffered, format=img_format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # تحديد نوع التحليل بناءً على الحالة الحالية
        if session['status'] == 'awaiting_first_image':
            # الصورة الأولى
            if timeframe and timeframe.upper() in ['M15', 'H4']:
                current_timeframe = timeframe.upper()
            else:
                current_timeframe = 'M15'  # افتراضي
            
            analysis = analyze_with_openai(img_str, img_format, current_timeframe)
            
            if current_timeframe == 'M15':
                session['m15_analysis'] = analysis
                session['status'] = 'awaiting_h4'
                next_step = "📈 الآن أرسل صورة الإطار 4 ساعات (H4) للإكمال"
            else:
                session['h4_analysis'] = analysis
                session['status'] = 'awaiting_m15'
                next_step = "📈 الآن أرسل صورة الإطار 15 دقيقة (M15) للإكمال"
            
            return jsonify({
                "message": f"✅ تم تحليل {current_timeframe} بنجاح",
                "analysis": analysis,
                "next_step": next_step,
                "status": session['status'],
                "user_id": user_id
            }), 200

        elif session['status'] == 'awaiting_m15':
            # الصورة الثانية - M15
            analysis = analyze_with_openai(img_str, img_format, "M15", session.get('h4_analysis'))
            session['m15_analysis'] = analysis
            session['status'] = 'completed'

            # تحليل نهائي موجز جداً
            final_analysis = f"""📊 **التحليل المتكامل:**

🕓 4 ساعات: {session['h4_analysis']}

⏱️ 15 دقيقة: {analysis}

🎯 **خلاصة:** تم تحليل الإطارين بنجاح. ركز على النقاط الرئيسية أعلاه."""
            
            # التأكد من الطول النهائي
            if len(final_analysis) > 1000:
                final_analysis = analyze_with_openai(img_str, img_format, "SUMMARY", f"H4: {session['h4_analysis']} M15: {analysis}")

            del analysis_sessions[user_id]

            return jsonify({
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "status": "completed"
            }), 200

        elif session['status'] == 'awaiting_h4':
            # الصورة الثانية - H4
            analysis = analyze_with_openai(img_str, img_format, "H4", session.get('m15_analysis'))
            session['h4_analysis'] = analysis
            session['status'] = 'completed'

            # تحليل نهائي موجز جداً
            final_analysis = f"""📊 **التحليل المتكامل:**

⏱️ 15 دقيقة: {session['m15_analysis']}

🕓 4 ساعات: {analysis}

🎯 **خلاصة:** تم تحليل الإطارين بنجاح. ركز على النقاط الرئيسية أعلاه."""
            
            # التأكد من الطول النهائي
            if len(final_analysis) > 1000:
                final_analysis = analyze_with_openai(img_str, img_format, "SUMMARY", f"M15: {session['m15_analysis']} H4: {analysis}")

            del analysis_sessions[user_id]

            return jsonify({
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "status": "completed"
            }), 200

        else:
            return jsonify({
                "message": "خطأ في تسلسل التحليل",
                "analysis": "الرجاء إرسال صورة للبدء"
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
