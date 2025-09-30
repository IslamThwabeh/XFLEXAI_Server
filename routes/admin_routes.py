# routes/admin_routes.py - Enhanced with security and better session handling
import os
import requests
import bcrypt
from datetime import datetime, timedelta
from flask import Blueprint, session, render_template, redirect, request, jsonify, url_for, flash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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

def require_admin_session():
    """Check if admin is logged in and session is valid"""
    if 'admin_id' not in session:
        return False
    return True

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # Clear any existing session
    if request.method == 'GET' and 'admin_id' in session:
        session.clear()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            return render_template('login.html', error='Username and password are required')

        try:
            admin = get_admin_by_username(username)
            if admin and bcrypt.checkpw(password.encode('utf-8'), admin[2].encode('utf-8')):
                session.clear()  # Clear any existing session data
                session['admin_id'] = admin[0]
                session['admin_username'] = admin[1]
                session['login_time'] = datetime.now().isoformat()
                session['last_activity'] = datetime.now().isoformat()
                session.permanent = True
                
                # Log successful login
                print(f"INFO: Admin '{username}' logged in successfully at {datetime.now()}")
                
                return redirect(url_for('admin_bp.admin_dashboard'))
            else:
                # Log failed login attempt
                print(f"WARNING: Failed login attempt for username '{username}' from IP {request.remote_addr}")
                return render_template('login.html', error='Invalid credentials')
        except Exception as e:
            print(f"ERROR: Login error for username '{username}': {e}")
            return render_template('login.html', error='Login error occurred')

    # Get message from query params (for session timeout)
    message = request.args.get('message')
    return render_template('login.html', message=message)

@admin_bp.route('/admin/dashboard')
def admin_dashboard():
    if not require_admin_session():
        return redirect(url_for('admin_bp.admin_login'))

    try:
        raw_users = get_users() or []
        raw_keys = get_registration_keys() or []
        
        # Format users with enhanced information
        display_users = []
        for u in raw_users:
            expiry = u.get('expiry_date')
            expiry_str = ''
            days_left = None
            status = 'Unknown'
            status_class = 'secondary'
            
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
                        
                        if expiry_dt > datetime.utcnow() and u.get('is_active', True):
                            status = 'Active'
                            status_class = 'success' if days_left > 7 else 'warning'
                        else:
                            status = 'Expired'
                            status_class = 'danger'
                    else:
                        expiry_str = str(expiry_dt)
                else:
                    expiry_str = 'N/A'
                    status = 'Inactive' if not u.get('is_active', True) else 'No expiry'
                    status_class = 'secondary'
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
                'status_class': status_class,
                'created_at': u.get('created_at')
            })

        # Format keys with enhanced information
        display_keys = []
        for k in raw_keys:
            created_date = k.get('created_at')
            if created_date and isinstance(created_date, datetime):
                created_str = created_date.strftime('%Y-%m-%d %H:%M')
            else:
                created_str = str(created_date) if created_date else 'N/A'
                
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
                'created_at': created_str,
                'is_active': k.get('is_active'),
                'is_deleted': k.get('is_deleted')
            })

        # Calculate dashboard statistics
        stats = {
            'total_users': len(display_users),
            'active_users': len([u for u in display_users if u['status'] == 'Active']),
            'expired_users': len([u for u in display_users if u['status'] == 'Expired']),
            'total_keys': len(display_keys),
            'unused_keys': len([k for k in display_keys if not k['used']]),
            'used_keys': len([k for k in display_keys if k['used']])
        }

        return render_template('dashboard.html',
                             admin_username=session.get('admin_username'),
                             users=display_users,
                             keys=display_keys,
                             stats=stats,
                             session_expires=session.get('last_activity'))
                             
    except Exception as e:
        print(f"ERROR: Dashboard error: {e}")
        return render_template('dashboard.html', error='Error loading dashboard data')

@admin_bp.route('/admin/generate-key', methods=['POST'])
def generate_key():
    """Generate a registration key with enhanced validation and logging"""
    if not require_admin_session():
        return jsonify({'success': False, 'error': 'Not authenticated'}), 403

    try:
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = {
                'duration': request.form.get('duration') or request.values.get('duration'),
                'telegram_identifier': request.form.get('telegram_identifier') or request.values.get('telegram_identifier')
            }

        # Validate and parse duration
        try:
            duration = int(data.get('duration', 1))
            if duration not in [1, 3, 6, 12]:
                return jsonify({'success': False, 'error': 'Invalid duration. Must be 1, 3, 6, or 12 months'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Duration must be a valid number'}), 400

        # Handle telegram identifier
        identifier = data.get('telegram_identifier')
        allowed_id = None
        if identifier:
            identifier = str(identifier).strip()
            if identifier.startswith('@'):
                try:
                    allowed_id = resolve_username_to_id(identifier)
                except Exception as e:
                    return jsonify({'success': False, 'error': f'Cannot resolve username: {str(e)}'}), 400
            else:
                try:
                    allowed_id = int(identifier)
                except (ValueError, TypeError):
                    return jsonify({'success': False, 'error': 'Invalid telegram identifier (must be numeric or @username)'}), 400

        # Generate unique key
        key = generate_unique_key()

        # Create registration key in database
        try:
            create_registration_key(key, duration, session['admin_id'], allowed_telegram_user_id=allowed_id)
            
            # Log key creation
            admin_username = session.get('admin_username', 'Unknown')
            print(f"INFO: Key '{key}' created by admin '{admin_username}' for {duration} months")
            
            return jsonify({
                'success': True, 
                'key': key, 
                'duration': duration,
                'allowed_telegram_user_id': allowed_id
            }), 200
            
        except Exception as e:
            print(f"ERROR: create_registration_key failed: {e}")
            return jsonify({'success': False, 'error': 'Failed to create key in database'}), 500

    except Exception as e:
        print(f"ERROR: Unexpected error in generate_key: {e}")
        return jsonify({'success': False, 'error': 'Unexpected server error'}), 500

@admin_bp.route('/admin/session-info')
def session_info():
    """Get current session information"""
    if not require_admin_session():
        return jsonify({'authenticated': False})
    
    last_activity = session.get('last_activity')
    if last_activity:
        last_activity_dt = datetime.fromisoformat(last_activity)
        time_left = (last_activity_dt + timedelta(minutes=15) - datetime.now()).total_seconds()
    else:
        time_left = 0
    
    return jsonify({
        'authenticated': True,
        'username

