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

    # Format users
    display_users = []
    from datetime import datetime
    for u in raw_users:
        expiry = u.get('expiry_date')
        expiry_str = ''
        days_left = None
        status = 'Unknown'
        try:
            if expiry:
                if isinstance(expiry, str):
                    try:
                        expiry_dt = datetime.fromisoformat(expiry)
                    except Exception:
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
            'registration_key_value': u.get('registration_key_value'),
            'registration_key_id': u.get('registration_key_id'),
            'expiry_date': expiry_str,
            'days_left': days_left,
            'is_active': u.get('is_active', True),
            'status': status,
            'created_at': u.get('created_at')
        })

    # Format keys
    display_keys = []
    for k in raw_keys:
        display_keys.append({
            'id': k.get('id'),
            'key_value': k.get('key_value'),
            'duration_months': k.get('duration_months'),
            'key_type_name': k.get('key_type_name'),
            'allowed_telegram_user_id': k.get('allowed_telegram_user_id'),
            'created_by_username': k.get('created_by_username') or 'System',
            'used': bool(k.get('used')),
            'used_by_telegram': k.get('used_by_telegram'),
            'used_at': k.get('used_at'),
            'created_at': k.get('created_at'),
            'is_active': k.get('is_active'),
            'is_deleted': k.get('is_deleted')
        })

    return render_template('dashboard.html',
                           admin_username=session.get('admin_username'),
                           users=display_users,
                           keys=display_keys)

@admin_bp.route('/admin/generate-key', methods=['POST'])
def generate_key():
    """
    Create a registration key. Accepts JSON or form:
      - duration (months)
      - telegram_identifier (optional): numeric id or @username
    Returns JSON and logs errors for debugging.
    """
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 403

    try:
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = {
                'duration': request.form.get('duration') or request.values.get('duration'),
                'telegram_identifier': request.form.get('telegram_identifier') or request.values.get('telegram_identifier')
            }

        # Log incoming payload for debugging
        print(f"DEBUG: generate-key payload: {data}", flush=True)

        # Parse duration
        try:
            duration = int(data.get('duration', 1))
        except Exception:
            duration = 1

        identifier = data.get('telegram_identifier')
        allowed_id = None
        if identifier:
            identifier = str(identifier).strip()
            # only resolve if starts with @ (public username)
            if identifier.startswith('@'):
                try:
                    allowed_id = resolve_username_to_id(identifier)
                except Exception as e:
                    print(f"ERROR: resolve_username_to_id failed: {e}", flush=True)
                    return jsonify({'success': False, 'error': f'Cannot resolve username: {str(e)}'}), 400
            else:
                try:
                    allowed_id = int(identifier)
                except Exception:
                    return jsonify({'success': False, 'error': 'Invalid telegram identifier (must be numeric or @username)'}), 400

        # generate unique key
        key = generate_unique_key()

        # insert into DB
        try:
            create_registration_key(key, duration, session['admin_id'], allowed_telegram_user_id=allowed_id)
        except Exception as e:
            # log full exception for Railway logs
            import traceback
            traceback_str = traceback.format_exc()
            print("ERROR: create_registration_key exception:\n", traceback_str, flush=True)
            return jsonify({'success': False, 'error': 'Server error while creating key'}), 500

        return jsonify({'success': True, 'key': key, 'allowed_telegram_user_id': allowed_id}), 200

    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        print("UNEXPECTED ERROR in generate_key:\n", traceback_str, flush=True)
        return jsonify({'success': False, 'error': 'Unexpected server error'}), 500

@admin_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

@admin_bp.route('/admin/create-first-admin')
def create_first_admin():
    username = "admin"
    password = "admin123"  # Change after first login

    existing = get_admin_by_username(username)
    if existing:
        return "Admin user already exists"

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_id = create_admin(username, hashed_password)
    return f"Admin user created! Username: {username}, Password: {password} - PLEASE CHANGE PASSWORD AFTER LOGIN!"


