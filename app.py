import os
from flask import Flask
from db import init_db
from openai_utils import init_openai
from admin import admin_bp
from routes import api_bp

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'fallback-secret-key-for-dev')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Initialize DB and OpenAI on startup
# NOTE: init_db() will raise if DB is unreachable.
init_db()
init_openai()

# Register blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # In Production use a proper WSGI server (gunicorn/uvicorn)
    app.run(host="0.0.0.0", port=port)
