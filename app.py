import os
import base64
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
from openai import OpenAI

# تهيئة Flask
app = Flask(__name__)

# تهيئة OpenAI Client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# تحديد حجم أقصى للرفع (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

@app.route('/')
def home():
    return "XFLEXAI Server is running ✅"

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

        # تحويل الصورة إلى Base64
        buffered = BytesIO()
        img.save(buffered, format=img.format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # إرسال إلى OpenAI لتحليل فني مضبوط
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "انت محلل فني محترف متخصص في قراءة الشارتات (MT4, TradingView)."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """قم بتحليل هذا الشارت باستخدام القالب التالي حصراً:

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

⚠️ ملاحظات:
- لا تكتب أي شيء خارج هذا القالب.
- التحليل يجب أن يكون عملي، مركز، ويعتمد على معطيات الشارت.
- أعطِ قيم واضحة (مثلاً RSI=49.59، دعم=3368، مقاومة=3388).
- استخدم لغة تقريرية احترافية مختصرة."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{img.format.lower()};base64,{img_str}"}
                        }
                    ]
                }
            ]
        )

        # استخراج التحليل من الرد
        analysis = response.choices[0].message.content.strip()

        return jsonify({"message": "✅ تم تحليل الشارت بنجاح", "analysis": analysis}), 200

    except Exception as e:
        return jsonify({"error": f"خطأ أثناء معالجة الصورة: {str(e)}"}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

