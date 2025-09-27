# app.py - main entry point
import os
from flask import Flask
from config import Config
from database.operations import init_database
from services.openai_service import init_openai
from routes.admin_routes import admin_bp
from routes.api_routes import api_bp

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

# Initialize DB and OpenAI on startup
init_database()
init_openai()

# Register blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Use a production WSGI server in production (gunicorn)
    app.run(host="0.0.0.0", port=port)
