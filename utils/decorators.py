# utils/decorators.py
from functools import wraps
from flask import request, jsonify
from database.operations import get_user_by_telegram_id
from datetime import datetime


def subscription_required(f):
    """
    Decorator to check for active user subscription.
    
    This decorator validates that:
    1. telegram_user_id is present in the request JSON
    2. The user is registered in the database
    3. The user's subscription has not expired
    
    If telegram_user_id is missing, the request is rejected with a 400 error.
    If the user is not registered or their subscription has expired, the request is rejected with a 403 error.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json() or {}
        telegram_user_id = data.get('telegram_user_id')

        # Check if telegram_user_id is provided
        if not telegram_user_id:
            return jsonify({
                'success': False,
                'code': 'missing_telegram_id',
                'message': 'Please include your telegram_user_id'
            }), 400

        # Validate telegram_user_id is a valid integer
        try:
            telegram_user_id = int(telegram_user_id)
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'message': 'Invalid telegram_user_id'
            }), 400

        # Check if user exists in database
        user = get_user_by_telegram_id(telegram_user_id)
        if not user:
            return jsonify({
                'success': False,
                'code': 'not_registered',
                'message': 'Your account is not registered. Please send your registration key using /redeem-key'
            }), 403

        # Check subscription expiry
        expiry = user.get('expiry_date')
        if expiry and isinstance(expiry, str):
            try:
                expiry = datetime.fromisoformat(expiry)
            except ValueError:
                # Handle cases where expiry might not be a valid ISO format string
                pass

        if not expiry or datetime.utcnow() > expiry:
            return jsonify({
                'success': False,
                'code': 'expired',
                'message': 'Your subscription has expired. Please renew or contact admin.'
            }), 403

        return f(*args, **kwargs)

    return decorated_function

