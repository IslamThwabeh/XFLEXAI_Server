import os

class Config:
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'fallback-secret-key-for-dev')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
