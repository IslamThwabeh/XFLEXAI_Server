# routes/admin_routes.py
import bcrypt
from flask import Blueprint, session, render_template, redirect, request, jsonify
from database.operations import get_admin_by_username, create_admin, create_registration_key, get_registration_keys, get_users
from services.key_service import generate_unique_key
import requests
import os

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

    users = get_users()
    keys = get_registration_keys()

    return render_template('dashboard.html',
                           admin_username=session.get('admin_username'),
                           users=users,
                           keys=keys)

@admin_bp.route('/admin/generate-key', methods=['POST'])
def generate_key():
    """
    Admin generates a registration key.
    Optional JSON fields:
      - duration (months)
      - telegram_identifier (optional): either numeric telegram id or @username. If provided and resolvable, the key will be pre-bound to that telegram id.
    """
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})

    data = request.get_json() or {}
    duration = int(data.get('duration', 1))
    identifier = data.get('telegram_identifier')  # either numeric id string or @username

    allowed_id = None
    if identifier:
        identifier = identifier.strip()
        if identifier.startswith('@'):
            try:
                allowed_id = resolve_username_to_id(identifier)
            except Exception as e:
                return jsonify({'success': False, 'error': f'Cannot resolve username: {str(e)}'}), 400
        else:
            try:
                allowed_id = int(identifier)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid telegram identifier'}), 400

    # Generate unique key
    key = generate_unique_key()
    # Insert key (allowed_id may be None)
    create_registration_key(key, duration, session['admin_id'], allowed_telegram_user_id=allowed_id)

    return jsonify({'success': True, 'key': key, 'allowed_telegram_user_id': allowed_id})
