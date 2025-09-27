# utils/helpers.py
import time
from services.openai_service import init_openai, OPENAI_AVAILABLE, openai_error_message, openai_last_check

def check_openai_status():
    """Refresh OpenAI status if older than 5 minutes and return status dict."""
    if time.time() - openai_last_check > 300:
        init_openai()
    return {
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message
    }
