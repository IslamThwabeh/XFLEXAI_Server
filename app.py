import os
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO

app = Flask(__name__)

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
        
        # Image is valid ✅
        # Here you can send it to AI analysis later
        return jsonify({"message": "الصورة صالحة! سيتم تحليلها الآن 🔄"}), 200

    except Exception as e:
        return jsonify({"error": "لم نتمكن من قراءة الصورة. الرجاء إرسال صورة صحيحة"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

