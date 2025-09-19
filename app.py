import os
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import base64
from openai import OpenAI

app = Flask(__name__)

# OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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

    # Try to open the file as an image
    try:
        img = Image.open(file.stream)
        # Optional: check format
        if img.format not in ['PNG', 'JPEG', 'JPG']:
            return jsonify({"error": "نوع الملف غير مدعوم. الرجاء إرسال PNG أو JPEG"}), 400

        # Convert image to base64 so we can send it to OpenAI
        file.stream.seek(0)
        img_bytes = file.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Call OpenAI Vision model
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Vision-capable model
            messages=[
                {
                    "role": "system",
                    "content": "أنت خبير تحليل فني للأسواق المالية. عندما تستقبل صورة شارت، قم بتحليلها بناءً على النماذج الفنية، المؤشرات، الدعم والمقاومة، الاتجاه العام، واستراتيجية التداول المحتملة."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "حلل هذا الشارت المرفق وأعطني تقرير مفصل:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]
                }
            ],
            max_tokens=500
        )

        ai_analysis = response.choices[0].message["content"]

        return jsonify({
            "message": "تم تحليل الصورة ✅",
            "analysis": ai_analysis
        }), 200

    except Exception as e:
        return jsonify({"error": f"لم نتمكن من قراءة الصورة. التفاصيل: {str(e)}"}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

