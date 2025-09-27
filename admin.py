import random
import string
import bcrypt
from flask import Blueprint, session, render_template, redirect, request, jsonify
from db import get_db_connection

admin_bp = Blueprint('admin', __name__)

def generate_short_key():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM admins WHERE username = %s', (username,))
        admin = cur.fetchone()
        cur.close()
        conn.close()

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

    conn = get_db_connection()
    cur = conn.cursor()

    # Get all users
    cur.execute('''
        SELECT u.*, rk.duration_months
        FROM users u
        LEFT JOIN registration_keys rk ON u.registration_key = rk.key_value
        ORDER BY u.created_at DESC
    ''')
    users = cur.fetchall()

    # Get generated keys
    cur.execute('''
        SELECT rk.*, a.username as created_by_username
        FROM registration_keys rk
        LEFT JOIN admins a ON rk.created_by = a.id
        ORDER BY rk.created_at DESC
    ''')
    keys = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('dashboard.html',
                          admin_username=session.get('admin_username'),
                          users=users,
                          keys=keys)

@admin_bp.route('/admin/generate-key', methods=['POST'])
def generate_key():
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})

    duration = request.json.get('duration', 1)

    # Generate unique key
    key = generate_short_key()
    is_unique = False

    conn = get_db_connection()
    cur = conn.cursor()

    while not is_unique:
        cur.execute('SELECT * FROM registration_keys WHERE key_value = %s', (key,))
        if cur.fetchone() is None:
            is_unique = True
        else:
            key = generate_short_key()

    # Insert the new key
    cur.execute(
        'INSERT INTO registration_keys (key_value, duration_months, created_by) VALUES (%s, %s, %s)',
        (key, duration, session['admin_id'])
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'success': True, 'key': key})

@admin_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

# Temporary route to create first admin (remove after use)
@admin_bp.route('/admin/create-first-admin')
def create_first_admin():
    username = "XFlexAdmin"
    password = "XFlexAI$$123456"

    conn = get_db_connection()
    cur = conn.cursor()

    # Check if admin already exists
    cur.execute('SELECT * FROM admins WHERE username = %s', (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return "Admin user already exists"

    # Create admin
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cur.execute(
        'INSERT INTO admins (username, password_hash) VALUES (%s, %s)',
        (username, hashed_password)
    )
    conn.commit()
    cur.close()
    conn.close()

    return f"Admin user created! Username: {username}, Password: {password} - PLEASE CHANGE PASSWORD AFTER LOGIN!"
