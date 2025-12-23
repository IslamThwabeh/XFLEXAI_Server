# utils/decorators.py
from functools import wraps
from flask import request, jsonify
from database.operations import get_user_by_telegram_id
from datetime import datetime

def subscription_required(f):
    """Decorator to check for active user subscription."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json() or {}
        telegram_user_id = data.get("telegram_user_id")

        if not telegram_user_id:
            return jsonify({"success": False, "code": "missing_telegram_id", "message": "Please include your telegram_user_id"}), 400

        try:
            telegram_user_id = int(telegram_user_id)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Invalid telegram_user_id"}), 400

        user = get_user_by_telegram_id(telegram_user_id)
        if not user:
            return jsonify({
                "success": False,
                "code": "not_registered",
                "message": "Your account is not registered. Please send your registration key using /redeem-key"
            }), 403

        expiry = user.get("expiry_date")
        if expiry and isinstance(expiry, str):
            try:
                expiry = datetime.fromisoformat(expiry)
            except ValueError:
                # Handle cases where expiry might not be a valid ISO format string
                pass

        if not expiry or datetime.utcnow() > expiry:
            return jsonify({
                "success": False,
                "code": "expired",
                "message": "Your subscription has expired. Please renew or contact admin."
            }), 403

        return f(*args, **kwargs)

    return decorated_function

