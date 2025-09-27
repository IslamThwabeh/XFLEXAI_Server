# utils/helpers.py
import time
from datetime import datetime
from services.openai_service import init_openai, OPENAI_AVAILABLE, openai_error_message, openai_last_check
from database.operations import get_user_by_telegram_id

def check_openai_status():
    """Refresh OpenAI status if older than 5 minutes and return status dict."""
    if time.time() - openai_last_check > 300:
        init_openai()
    return {
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message
    }

def is_user_active_and_days_left(telegram_user_id):
    """
    Returns (active: bool, days_left: int or None, expiry_date: datetime or None)
    """
    row = get_user_by_telegram_id(telegram_user_id)
    if not row:
        return False, None, None
    expiry = row.get('expiry_date')
    if not expiry:
        return False, None, None
    now = datetime.utcnow()
    days_left = (expiry - now).days
    active = expiry > now and row.get('is_active', True)
    return active, days_left, expiry
