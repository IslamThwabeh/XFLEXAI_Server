import os
import base64
import requests
import time
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
from datetime import datetime

# Initialize Flask
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max

# Session store (in-memory)
analysis_sessions = {}

# OpenAI client setup
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
        if not api_key:
            openai_error_message = "OpenAI API key not configured"
            return False

        client = OpenAI(api_key=api_key)

        # Quick test
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        if "gpt-4o" not in model_ids:
            openai_error_message = "GPT-4o not available"
            return False

        OPENAI_AVAILABLE = True
        openai_error_message = ""
        openai_last_check = time.time()
        return True
    except Exception as e:
        openai_error_message = f"OpenAI init error: {str(e)}"
        return False


# Init once at startup
init_openai()


def split_text_for_telegram(text, limit=3500):
    """Split long analysis into chunks safe for Telegram/SendPulse"""
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    return chunks


def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, mode="pro"):
    """Analyze image with OpenAI with enhanced prompts"""

    if mode == "student":
        analysis_prompt = """
أنت مدرب تحليل فني، مهمتك شرح الشارت لطلاب مبتدئين.
استخدم لغة مبسطة، خطوة بخطوة:
1. ما الذي نراه على الشارت (اتجاه صاعد/هابط)
2. أهم الدعوم والمقاومات
3. نموذج فني أو شمعة مهمة
4. ماذا يعني هذا للمتداول؟
5. نصيحة قصيرة

تجنب المصطلحات المعقدة. اجعل الإجابة تعليمية وواضحة.
"""
    elif timeframe == "H4" and previous_analysis:
        analysis_prompt = f"""
بناءً على تحليل 15 دقيقة السابق:
{previous_analysis}

الآن قم بتحليل شارت 4 ساعات باستخدام Smart Money Concepts (SMC) ومستويات فيبوناتشي:
- Order Blocks
- Liquidity Zones
- Market Structure Shifts
- Fibonacci Retracements/Extensions
ثم قدّم توصية استراتيجية شاملة مبسطة.
"""
    else:
        analysis_prompt = """
أنت محلل فني محترف متخصص في تحليل شارتات التداول.
حدد:
- الاتجاه العام
- الدعوم والمقاومات
- نموذج أو مؤشر فني واضح
- استراتيجية تداول محتملة
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "أنت محلل فني محترف للأسواق المالية."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": analysis_prompt},
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
        temperature=0.6
    )

    full_text = response.choices[0].message.content.strip()
    return split_text_for_telegram(full_text)


@app.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"


@app.route('/sendpulse-analyze', methods=['POST'])
def sendpulse_analyze():
    """
    Unified endpoint:
    - Accepts multipart/form-data (file upload)
    - Accepts JSON with image_url
    """
    try:
        user_id = request.form.get('user_id') or request.json.get('user_id') if request.is_json else "default_user"
        timeframe = request.form.get('timeframe') or (request.json.get('timeframe') if request.is_json else None)
        mode = request.form.get('mode') or (request.json.get('mode') if request.is_json else "pro")

        # --- Case 1: File Upload ---
        if 'file' in request.files:
            file = request.files['file']
            img = Image.open(file.stream)
        else:
            # --- Case 2: JSON image_url ---
            data = request.get_json()
            if not data or not data.get("image_url"):
                return jsonify({"error": "No file or image_url provided"}), 400
            response = requests.get(data["image_url"], timeout=10)
            if response.status_code != 200:
                return jsonify({"error": "Failed to download image"}), 400
            img = Image.open(BytesIO(response.content))

        if img.format not in ['PNG', 'JPEG', 'JPG']:
            return jsonify({"error": "Unsupported format"}), 400

        if not OPENAI_AVAILABLE:
            return jsonify({"error": openai_error_message}), 503

        # Convert image to base64
        buffered = BytesIO()
        img.save(buffered, format=img.format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Session init
        if user_id not in analysis_sessions:
            analysis_sessions[user_id] = {
                "m15_analysis": None,
                "h4_analysis": None,
                "created_at": datetime.now(),
                "status": "awaiting_m15"
            }

        session = analysis_sessions[user_id]

        if session["status"] == "awaiting_m15" or not timeframe:
            # First image (M15)
            analysis_chunks = analyze_with_openai(img_str, img.format, "M15", mode=mode)
            session["m15_analysis"] = "\n".join(analysis_chunks)
            session["status"] = "awaiting_h4"

            return jsonify({
                "message": "✅ M15 chart analyzed",
                "analysis_chunks": analysis_chunks,
                "next_step": "Please send H4 chart",
                "status": "awaiting_h4"
            }), 200

        elif session["status"] == "awaiting_h4" and timeframe == "H4":
            # Second image (H4)
            analysis_chunks = analyze_with_openai(img_str, img.format, "H4", previous_analysis=session["m15_analysis"], mode=mode)
            session["h4_analysis"] = "\n".join(analysis_chunks)
            session["status"] = "completed"

            final_analysis = f"""
## 📊 التحليل المتكامل

### ⏱️ M15:
{session['m15_analysis']}

### 🕓 H4:
{session['h4_analysis']}

🎯 التوصية النهائية:
- نقاط دخول وخروج
- إدارة المخاطرة
- أهداف ربح محتملة
"""

            # Cleanup
            del analysis_sessions[user_id]

            return jsonify({
                "message": "✅ Full multi-timeframe analysis complete",
                "analysis_chunks": split_text_for_telegram(final_analysis),
                "status": "completed"
            }), 200

        else:
            return jsonify({"error": "Wrong sequence. Start with M15 first."}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    count = len(analysis_sessions)
    analysis_sessions.clear()
    return jsonify({"message": f"Cleared {count} sessions"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

