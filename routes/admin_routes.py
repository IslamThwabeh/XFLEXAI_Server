# routes/admin_routes.py
import bcrypt
from flask import Blueprint, session, render_template, redirect, request, jsonify
from database.operations import get_admin_by_username, create_admin, create_registration_key, get_registration_keys, get_users
from services.key_service import generate_unique_key, calculate_expiry_date

admin_bp = Blueprint('admin_bp', __name__)

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
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})

    duration = request.json.get('duration', 1)
    key = generate_unique_key()
    create_registration_key(key, duration, session['admin_id'])
    expiry_date = calculate_expiry_date(duration)
    return jsonify({'success': True, 'key': key, 'expiry': expiry_date.strftime('%Y-%m-%d')})

@admin_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

@admin_bp.route('/admin/create-first-admin')
def create_first_admin():
    username = "XFlexAdmin"
    password = "XFlexAI$$123456"  # change after first login

    existing = get_admin_by_username(username)
    if existing:
        return "Admin user already exists"

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_id = create_admin(username, hashed_password)
    return f"Admin user created! Username: {username}, Password: {password} - PLEASE CHANGE PASSWORD AFTER LOGIN!"
