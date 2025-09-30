# config.py
import os
from datetime import timedelta

class Config:
    # Basic Configuration
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'fallback-secret-key-for-dev')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=15)  # 15 minute timeout
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Security Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    
    # Rate Limiting Configuration
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_DEFAULT = "100 per hour"

