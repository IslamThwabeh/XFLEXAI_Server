# app.py - main entry point with enhanced security and session management
import os
from datetime import datetime, timedelta
from flask import Flask, session, request, g, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from config import Config
from database.operations import init_database
from services.openai_service import init_openai
from routes.admin_routes import admin_bp
from routes.api_routes import api_bp

app = Flask(__name__)
app.config.from_object(Config)

# Initialize security extensions
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Session configuration
app.permanent_session_lifetime = Config.PERMANENT_SESSION_LIFETIME

# Session middleware for automatic timeout handling
@app.before_request
def check_session_timeout():
    """Check and handle session timeout"""
    # Skip for API routes and static files
    if (request.endpoint and
        (request.endpoint.startswith('api_bp.') or
         request.endpoint.startswith('static') or
         request.endpoint == 'admin_bp.admin_login')):
        return

    # Check if admin session exists and is valid
    if 'admin_id' in session:
        if 'last_activity' in session:
            time_since_activity = datetime.now() - datetime.fromisoformat(session['last_activity'])
            if time_since_activity > Config.PERMANENT_SESSION_LIFETIME:
                session.clear()
                if request.endpoint == 'admin_bp.admin_dashboard':
                    return redirect(url_for('admin_bp.admin_login', message='Session expired'))

        # Update last activity
        session['last_activity'] = datetime.now().isoformat()
        session.permanent = True

@app.after_request
def security_headers(response):
    """Add security headers"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Initialize DB and OpenAI on startup
init_database()
init_openai()

# Register blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)

@app.errorhandler(429)
def ratelimit_handler(e):
    return {"error": "Rate limit exceeded", "message": str(e.description)}, 429

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get('FLASK_ENV') == 'development')
