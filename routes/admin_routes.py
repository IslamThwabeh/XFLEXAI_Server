# routes/admin_routes.py
import os
import requests
import bcrypt
from flask import Blueprint, session, render_template, redirect, request, jsonify
from database.operations import (
    get_admin_by_username,
    create_admin,
    create_registration_key,
    get_registration_keys,
    get_users
)
from services.key_service import generate_unique_key

admin_bp = Blueprint('admin_bp', __name__)

def resolve_username_to_id(username):
    """
    Resolve a public Telegram @username to numeric id using Telegram Bot API.
    Returns numeric id or raises an exception.
    """
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    if not username.startswith('@'):
        username = '@' + username
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
    resp = requests.get(url, params={"chat_id": username}, timeout=10)
    data = resp.json()
    if resp.status_code == 200 and data.get("ok"):
        return data["result"]["id"]
    raise RuntimeError(f"Failed to resolve username {username}: {data}")

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        admin = get_admin_by_username(username)
        if admin and bcrypt.checkpw(password.encode('utf-8'), admin[2].encode('utf-8')):
            session['admin_id'] = admin[0]
            session['admin_username'] = admin[1]
            return redirect('/admin/dashboard')
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')

@admin_bp.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    raw_users = get_users() or []
    raw_keys = get_registration_keys() or []

    # Normalize and format user rows for display
    display_users = []
    from datetime import datetime
    for u in raw_users:
        expiry = u.get('expiry_date')
        expiry_dt = None
        expiry_str = ''
        days_left = None
        status = 'Unknown'
        try:
            if expiry:
                if isinstance(expiry, str):
                    try:
                        expiry_dt = datetime.fromisoformat(expiry)
                    except Exception:
                        # fallback if format differs
                        expiry_dt = expiry
                else:
                    expiry_dt = expiry
                if hasattr(expiry_dt, 'strftime'):
                    expiry_str = expiry_dt.strftime('%Y-%m-%d %H:%M:%S')
                    days_left = (expiry_dt - datetime.utcnow()).days
                    status = 'Active' if expiry_dt > datetime.utcnow() and u.get('is_active', True) else 'Expired'
                else:
                    expiry_str = str(expiry_dt)
            else:
                expiry_str = 'N/A'
                status = 'Inactive' if not u.get('is_active', True) else 'No expiry'
        except Exception:
            expiry_str = str(expiry)

        display_users.append({
            'telegram_user_id': u.get('telegram_user_id'),
            'registration_key': u.get('registration_key'),
            'expiry_date': expiry_str,
            'days_left': days_left,
            'is_active': u.get('is_active', True),
            'status': status,
            'created_at': u.get('created_at')
        })

    # Normalize and format registration keys
    display_keys = []
    for k in raw_keys:
        created_at = k.get('created_at')
        created_str = ''
        try:
            if created_at:
                if isinstance(created_at, str):
                    created_str = created_at
                else:
                    created_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            created_str = str(created_at)

        display_keys.append({
            'key_value': k.get('key_value'),
            'duration_months': k.get('duration_months'),
            'created_by_username': k.get('created_by_username') or 'System',
            'used': bool(k.get('used')),
            'used_by': k.get('used_by'),
            'allowed_telegram_user_id': k.get('allowed_telegram_user_id'),
            'created_at': created_str
        })

    return render_template('dashboard.html',
                           admin_username=session.get('admin_username'),
                           users=display_users,
                           keys=display_keys)

@admin_bp.route('/admin/generate-key', methods=['POST'])
def generate_key():
    """
    Admin generates a registration key.
    Accepts JSON or form data:
      - duration (months)
      - telegram_identifier (optional): numeric telegram id or @username
    Returns JSON with success/error and helpful messages.
    """
    # Authentication check
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 403

    # Accept JSON or form-data for compatibility
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = {
            'duration': request.form.get('duration') or request.values.get('duration'),
            'telegram_identifier': request.form.get('telegram_identifier') or request.values.get('telegram_identifier')
        }

    # Parse duration safely
    try:
        duration = int(data.get('duration', 1))
    except Exception:
        duration = 1

    identifier = data.get('telegram_identifier')
    allowed_id = None

    # Resolve identifier if provided
    if identifier:
        identifier = str(identifier).strip()
        if identifier.startswith('@'):
            try:
                allowed_id = resolve_username_to_id(identifier)
            except Exception as e:
                # Return clear JSON error so frontend can surface it
                return jsonify({'success': False, 'error': f'Cannot resolve username: {str(e)}'}), 400
        else:
            try:
                allowed_id = int(identifier)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid telegram identifier'}), 400

    # Generate unique key
    try:
        key = generate_unique_key()
    except Exception as e:
        print(f"ERROR: generate_unique_key failed: {e}", flush=True)
        return jsonify({'success': False, 'error': 'Failed to generate key'}), 500

    # Insert key into DB, with allowed_telegram_user_id possibly None
    try:
        # create_registration_key signature: (key_value, duration_months, created_by, allowed_telegram_user_id=None)
        create_registration_key(key, duration, session['admin_id'], allowed_telegram_user_id=allowed_id)
    except Exception as e:
        # Log the exception to server logs (Railway logs)
        print(f"ERROR: create_registration_key failed: {e}", flush=True)
        # Return JSON instead of HTML error page
        return jsonify({'success': False, 'error': 'Failed to create registration key on the server'}), 500

    # Success response
    return jsonify({'success': True, 'key': key, 'allowed_telegram_user_id': allowed_id}), 200

@admin_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

@admin_bp.route('/admin/create-first-admin')
def create_first_admin():
    username = "admin"
    password = "admin123"  # Change this after first login

    existing = get_admin_by_username(username)
    if existing:
        return "Admin user already exists"

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_id = create_admin(username, hashed_password)
    return f"Admin user created! Username: {username}, Password: {password} - PLEASE CHANGE PASSWORD AFTER LOGIN!"
