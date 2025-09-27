import os
import base64
import re
import requests
import json
import psycopg2
import bcrypt
import random
import string
from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from PIL import Image
from io import BytesIO
import time
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'fallback-secret-key-for-dev')

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

analysis_sessions = {}

OPENAI_AVAILABLE = False
client = None
openai_error_message = ""
openai_last_check = 0

# Database connection function
def get_db_connection():
    db_url = os.getenv('DATABASE_URL')
    print(f"DEBUG: DATABASE_URL is '{db_url}'")  # Logging the env variable
    try:
        conn = psycopg2.connect(db_url)
        print("DEBUG: Successfully connected to the database.")
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to the database: {e}")
        raise

# Initialize database tables
def init_db():
    print("DEBUG: Starting database initialization.")
    try:
        conn = get_db_connection()
        print("DEBUG: Connection object:", conn)
        cur = conn.cursor()
        print("DEBUG: Cursor object created.")

        # Create tables if they don't exist
        cur.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_user_id BIGINT UNIQUE NOT NULL,
                registration_key VARCHAR(20) UNIQUE NOT NULL,
                expiry_date TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS registration_keys (
                id SERIAL PRIMARY KEY,
                key_value VARCHAR(20) UNIQUE NOT NULL,
                duration_months INTEGER NOT NULL,
                created_by INTEGER REFERENCES admins(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used BOOLEAN DEFAULT FALSE,
                used_by INTEGER REFERENCES users(id),
                used_at TIMESTAMP
            )
        ''')

        conn.commit()
        cur.close()
        conn.close()
        print("DEBUG: Database tables initialized successfully")
    except Exception as e:
        print(f"ERROR: Database initialization failed: {e}")
        raise

# Generate short registration key (6 characters)
def generate_short_key():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

# Initialize database on startup
init_db()

def init_openai():
    global OPENAI_AVAILABLE, client, openai_error_message, openai_last_check

    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "OpenAI API key not configured"
            return False

        client = OpenAI(api_key=api_key)

        try:
            models = client.models.list()
            model_ids = [model.id for model in models.data]
            if "gpt-4o" not in model_ids:
                openai_error_message = "GPT-4o model not available in your account"
                return False

            OPENAI_AVAILABLE = True
            openai_error_message = ""
            openai_last_check = time.time()
            return True

        except Exception as e:
            error_msg = str(e)
            if "insufficient_quota" in error_msg:
                openai_error_message = "Account has no API credits. Please add funds to your OpenAI API account."
            elif "invalid_api_key" in error_msg:
                openai_error_message = "Invalid API key. Please check your OPENAI_API_KEY environment variable."
            else:
                openai_error_message = f"OpenAI API test failed: {error_msg}"
            return False

    except ImportError:
        openai_error_message = "OpenAI package not installed"
        return False
    except Exception as e:
        openai_error_message = f"OpenAI initialization error: {str(e)}"
        return False

init_openai()

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, user_analysis=None, action_type="chart_analysis"):
    """تحليل الصورة أو النص مع إجبار OpenAI على الالتزام بعدد أحرف محدد"""

    if action_type == "user_analysis_feedback":
        # تحليل وتقييم تحليل المستخدم
        char_limit = 800
        analysis_prompt = f"""
أنت خبير تحليل فني. قم بتقييم تحليل المستخدم التالي وتقديم ملاحظات بناءة:

تحليل المستخدم:
{user_analysis}

**التزم الصارم بالشروط التالية:**
1. لا تتجاوز {char_limit} حرف تحت أي ظرف
2. قدم نقاط قوة التحليل
3. قدم نقاط تحسين مع شرح موجز
4. قدم نصيحة عملية واحدة

**تأكد من عد الأحرف والالتزام بالحد {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    elif timeframe == "H4" and previous_analysis:
        # التحليل النهائي بعد جمع الإطارين
        char_limit = 800
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً نهائياً موجزاً جداً يجمع بين الإطارين.

التحليل السابق (15 دقيقة): {previous_analysis[:150]}...

**التزم الصارم بالشروط التالية:**
1. لا تتجاوز {char_limit} حرف تحت أي ظرف
2. دمج الرؤيات من الإطارين
3. تقديم توصية تداول واحدة واضحة
4. ذكر إدارة المخاطرة باختصار

**المطلوب في 3 نقاط فقط:**
1. الصورة الكلية من الإطارين
2. التوصية الاستراتيجية
3. إدارة المخاطرة

**تأكد من عد الأحرف والالتزام بالحد {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    else:
        # التحليل الأولي للإطار الواحد
        char_limit = 600
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً دقيقاً ومختصراً للغاية للشارت.

**التزم الصارم بالشروط التالية:**
1. لا تتجاوز {char_limit} حرف تحت أي ظرف
2. ركز على النقاط العملية فقط
3. استخدم لغة مختصرة جداً

**المطلوب في 4 نقاط فقط:**
1. الاتجاه العام (سطر واحد)
2. أهم مستوى دعم ومقاومة (سطر واحد)
3. توصية تداول واضحة (سطر واحد)
4. إدارة المخاطرة (سطر واحد)

**تأكد من عد الأحرف والالتزام بالحد {char_limit} حرف.**
"""
        max_tokens = char_limit // 2 + 50

    if image_str:  # إذا كان هناك صورة للتحليل
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"أنت محلل فني محترف. التزم الصارم بعدم تجاوز {char_limit} حرف في ردك."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": analysis_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format.lower()};base64,{image_str}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
    else:  # إذا كان تحليل نصي فقط
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"أنت محلل فني محترف. التزم الصارم بعدم تجاوز {char_limit} حرف في ردك."
                },
                {
                    "role": "user",
                    "content": analysis_prompt
                }
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )

    analysis = response.choices[0].message.content.strip()

    # التحقق من الالتزام بالحد (آلية احتياطية)
    if len(analysis) > char_limit + 100:
        retry_prompt = f"""
التحليل السابق كان طويلاً جداً ({len(analysis)} حرف). أعد كتابته مع الالتزام بعدم تجاوز {char_limit} حرف:

{analysis}
"""
        retry_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"اختصار النص إلى {char_limit} حرف."},
                {"role": "user", "content": retry_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        analysis = retry_response.choices[0].message.content.strip()

    return analysis

# ==================== ADMIN ROUTES ====================

@app.route('/admin/login', methods=['GET', 'POST'])
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

@app.route('/admin/dashboard')
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
                         admin_username=session['admin_username'],
                         users=users,
                         keys=keys)

@app.route('/admin/generate-key', methods=['POST'])
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

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

# Temporary route to create first admin (remove after use)
@app.route('/admin/create-first-admin')
def create_first_admin():
    username = "admin"
    password = "admin123"  # Change this after first login

    conn = get_db_connection()
    cur = conn.cursor()

    # Check if admin already exists
    cur.execute('SELECT * FROM admins WHERE username = %s', (username,))
    if cur.fetchone():
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

# ==================== API ROUTES ====================

@app.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

@app.route('/analyze', methods=['POST'])
def analyze():
    """Endpoint رئيسي جديد يدعم جميع أنواع التحليل"""
    try:
        if not request.is_json:
            return jsonify({
                "success": False,
                "message": "نوع المحتوى غير مدعوم",
                "analysis": "يجب أن يكون الطلب بتنسيق JSON"
            }), 415

        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "message": "لم يتم إرسال بيانات",
                "analysis": "لم يتم إرسال بيانات للتحليل"
            }), 400

        user_id = data.get('user_id', 'default_user')
        action_type = data.get('action_type', 'chart_analysis')  # chart_analysis, add_timeframe, user_analysis
        image_url = data.get('image_url')
        user_analysis_text = data.get('user_analysis')
        timeframe = data.get('timeframe', 'M15')

        if not image_url and not user_analysis_text:
            return jsonify({
                "success": False,
                "message": "بيانات غير كافية",
                "analysis": "يجب تقديم صورة أو تحليل نصي"
            }), 400

        # تهيئة جلسة المستخدم
        if user_id not in analysis_sessions:
            analysis_sessions[user_id] = {
                'user_id': user_id,
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'created_at': datetime.now(),
                'status': 'ready',
                'conversation_history': []
            }

        session_data = analysis_sessions[user_id]

        # تحميل الصورة إذا وجدت
        image_str = None
        image_format = None
        if image_url:
            try:
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    if img.format in ['PNG', 'JPEG', 'JPG']:
                        buffered = BytesIO()
                        img_format = img.format if img.format else 'JPEG'
                        img.save(buffered, format=img_format)
                        image_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            except Exception as e:
                print(f"Error loading image: {e}")

        if not OPENAI_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": openai_error_message
            }), 503

        # معالجة أنواع الإجراءات المختلفة
        if action_type == 'chart_analysis':
            # تحليل الرسم البياني الأول
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "تعذر تحميل الصورة المطلوبة"
                }), 400

            analysis = analyze_with_openai(image_str, img_format, timeframe)
            session_data['first_analysis'] = analysis
            session_data['first_timeframe'] = timeframe
            session_data['status'] = 'first_analysis_done'

            # إضافة إلى سجل المحادثة
            session_data['conversation_history'].append({
                'type': 'analysis',
                'timeframe': timeframe,
                'content': analysis,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": f"✅ تم تحليل {timeframe} بنجاح",
                "analysis": analysis,
                "user_id": user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "add_timeframe", "label": "➕ إضافة إطار زمني آخر"},
                    {"action": "user_analysis", "label": "📝 إضافة تحليلي الشخصي"}
                ]
            }), 200

        elif action_type == 'add_timeframe':
            # إضافة إطار زمني ثاني
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "تعذر تحميل الصورة المطلوبة"
                }), 400

            if session_data['status'] != 'first_analysis_done':
                return jsonify({
                    "success": False,
                    "message": "خطأ في التسلسل",
                    "analysis": "يجب تحليل الإطار الأول قبل إضافة الثاني"
                }), 400

            # تحديد الإطار الزمني التلقائي (المعاكس للأول)
            if session_data['first_timeframe'] == 'M15':
                new_timeframe = 'H4'
            else:
                new_timeframe = 'M15'

            analysis = analyze_with_openai(image_str, img_format, new_timeframe, session_data['first_analysis'])
            session_data['second_analysis'] = analysis
            session_data['second_timeframe'] = new_timeframe
            session_data['status'] = 'both_analyses_done'

            # التحليل النهائي التجميعي
            final_analysis = analyze_with_openai(
                None, None, "H4",
                f"{session_data['first_timeframe']}: {session_data['first_analysis']}",
                None, "chart_analysis"
            )

            # إضافة إلى سجل المحادثة
            session_data['conversation_history'].append({
                'type': 'analysis',
                'timeframe': new_timeframe,
                'content': analysis,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "user_id": user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "user_analysis", "label": "📝 إضافة تحليلي الشخصي للحصول على تقييم"}
                ]
            }), 200

        elif action_type == 'user_analysis':
            # تقييم تحليل المستخدم
            if not user_analysis_text:
                return jsonify({
                    "success": False,
                    "message": "تحليل نصي مطلوب",
                    "analysis": "يرجى تقديم تحليلك النصي"
                }), 400

            feedback = analyze_with_openai(
                image_str, img_format if image_str else None,
                None, None, user_analysis_text, "user_analysis_feedback"
            )

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'user_analysis_reviewed'

            # إضافة إلى سجل المحادثة
            session_data['conversation_history'].append({
                'type': 'user_analysis',
                'content': user_analysis_text,
                'feedback': feedback,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "user_id": user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "new_analysis", "label": "🔄 بدء تحليل جديد"}
                ]
            }), 200

        elif action_type == 'new_analysis':
            # بدء جلسة تحليل جديدة
            analysis_sessions[user_id] = {
                'user_id': user_id,
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'created_at': datetime.now(),
                'status': 'ready',
                'conversation_history': session_data.get('conversation_history', [])
            }

            return jsonify({
                "success": True,
                "message": "🔄 تم بدء جلسة تحليل جديدة",
                "analysis": "يمكنك الآن إرسال صورة الرسم البياني للتحليل",
                "user_id": user_id,
                "status": 'ready',
                "next_actions": [
                    {"action": "chart_analysis", "label": "📊 تحليل رسم بياني", "requires_image": True}
                ]
            }), 200

        else:
            return jsonify({
                "success": False,
                "message": "نوع إجراء غير معروف",
                "analysis": f"نوع الإجراء {action_type} غير مدعوم"
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"خطأ أثناء المعالجة: {str(e)}",
            "analysis": f"فشل في التحليل: {str(e)}"
        }), 400

# دعم التوافق مع الإصدار القديم
@app.route('/sendpulse-analyze', methods=['POST'])
def sendpulse_analyze():
    """Endpoint للتوافق مع الإصدار القديم"""
    data = request.get_json()
    if data:
        # تحويل الطلب القديم إلى التنسيق الجديد
        data['action_type'] = 'chart_analysis'
        if 'timeframe' not in data:
            data['timeframe'] = 'M15'
    return analyze()

@app.route('/multi-timeframe-analyze', methods=['POST'])
def multi_timeframe_analyze():
    """Endpoint للتواسب مع الطلبات متعددة الأطر"""
    return sendpulse_analyze()

@app.route('/user-analysis', methods=['POST'])
def user_analysis():
    """Endpoint مخصص لتحليل المستخدم"""
    data = request.get_json()
    if data:
        data['action_type'] = 'user_analysis'
    return analyze()

@app.route('/status')
def status():
    if time.time() - openai_last_check > 300:
        init_openai()

    return jsonify({
        "server": "running",
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message,
        "active_sessions": len(analysis_sessions),
        "timestamp": time.time()
    })

@app.route('/session-info/<user_id>')
def session_info(user_id):
    """الحصول على معلومات جلسة مستخدم معين"""
    if user_id in analysis_sessions:
        session_data = analysis_sessions[user_id].copy()
        # إخفاء البيانات الحساسة للعرض
        if 'conversation_history' in session_data:
            session_data['conversation_count'] = len(session_data['conversation_history'])
            del session_data['conversation_history']
        return jsonify({"success": True, "session": session_data})
    else:
        return jsonify({"success": False, "message": "الجلسة غير موجودة"})

@app.route('/clear-sessions')
def clear_sessions():
    global analysis_sessions
    count = len(analysis_sessions)
    analysis_sessions = {}
    return jsonify({
        "message": f"تم مسح {count} جلسة",
        "status": "sessions_cleared"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
