import os
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import base64
import openai

app = Flask(__name__)

# OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Limit upload size (optional, in bytes)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB max

@app.route('/')
def home():
    return "XFLEXAI Server is running ✅"

# Endpoint for image upload
@app.route('/analyze', methods=['POST'])
def analyze_image():
    if 'file' not in request.files:
        return jsonify({"error": "لم يتم إرسال صورة. الرجاء إرسال صورة واضحة"}), 400

    file = request.files['file']

    try:
        img = Image.open(file.stream)
        if img.format not in ['PNG', 'JPEG', 'JPG']:
            return jsonify({"error": "نوع الملف غير مدعوم. الرجاء إرسال PNG أو JPEG"}), 400

        # Convert image to base64
        buffered = BytesIO()
        img.save(buffered, format=img.format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Send to OpenAI for technical chart analysis
        response = openai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "انت محلل فني محترف متخصص في قراءة الشارتات (MT4, TradingView)."},
                {"role": "user", "content": [
                    {"type": "text", "text": """قم بتحليل هذا الشارت بنفس القالب التالي حصراً (ولا تخرج عنه):

### الإطار الزمني
...

### النماذج الفنية
...

### المؤشرات الفنية
...

### مستويات الدعم والمقاومة
...

### الاتجاه العام
...

### استراتيجية التداول المحتملة
...

### ملاحظات عامة
...

⚠️ انتبه: يجب أن يكون التحليل مركز وعملي، ومطابق لأسلوب التحليل الفني المتعارف عليه، مثل المثال التالي:
- RSI بقيمة 49.59 → السوق متوازن.
- دعم عند 3368 ومقاومة عند 3388.
- الاتجاه جانبي.
- إستراتيجية محتملة: انتظار كسر الدعم أو المقاومة.

ها هو الشارت للتحليل:"""},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                ]}
            ]
        )

        analysis = response.choices[0].message.content

        return jsonify({"message": "✅ تم تحليل الشارت بنجاح", "analysis": analysis}), 200

    except Exception as e:
        return jsonify({"error": f"خطأ أثناء معالجة الصورة: {str(e)}"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

