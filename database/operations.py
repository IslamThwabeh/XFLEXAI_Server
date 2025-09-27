# database/operations.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import datetime, timedelta

def get_db_connection():
    """Get a new psycopg2 connection using Config.DATABASE_URL."""
    db_url = Config.DATABASE_URL
    print(f"DEBUG: DATABASE_URL (from config) is '{db_url}'")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured in environment")
    return psycopg2.connect(db_url)

def init_database():
    """Initialize database tables (safe to call on startup)."""
    from database.models import get_table_definitions
    print("DEBUG: Starting database initialization (init_database).")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        tables = get_table_definitions()
        for name, ddl in tables.items():
            cur.execute(ddl)
            print(f"DEBUG: Ensured table {name}")
        conn.commit()
        cur.close()
        print("DEBUG: Database tables created/ensured.")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: init_database failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

def execute_query(query, params=None, fetch=False, dict_cursor=False):
    """
    Generic function to execute queries.
    - fetch=True returns cur.fetchall()
    - dict_cursor=True returns list of dicts (uses RealDictCursor)
    """
    conn = None
    try:
        conn = get_db_connection()
        if dict_cursor:
            cur = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(query, params or ())
        result = None
        if fetch:
            result = cur.fetchall()
        conn.commit()
        cur.close()
        return result
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: execute_query failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Admin operations
def get_admin_by_username(username):
    rows = execute_query("SELECT * FROM admins WHERE username = %s", (username,), fetch=True)
    if rows:
        return rows[0]  # tuple (id, username, password_hash, created_at)
    return None

def create_admin(username, password_hash):
    # Return newly created id
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO admins (username, password_hash) VALUES (%s, %s) RETURNING id', (username, password_hash))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return new_id
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: create_admin failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Registration key operations
def create_registration_key(key_value, duration_months, created_by, allowed_telegram_user_id=None):
    """
    Insert a registration key record.
    allowed_telegram_user_id may be None (not bound yet) or a numeric Telegram id.
    """
    return execute_query(
        "INSERT INTO registration_keys (key_value, duration_months, created_by, allowed_telegram_user_id) VALUES (%s, %s, %s, %s)",
        (key_value, duration_months, created_by, allowed_telegram_user_id)
    )

def get_registration_keys():
    return execute_query(
        "SELECT rk.*, a.username as created_by_username FROM registration_keys rk LEFT JOIN admins a ON rk.created_by = a.id ORDER BY rk.created_at DESC",
        fetch=True,
        dict_cursor=True
    )

def get_registration_key_by_value(key_value):
    rows = execute_query("SELECT * FROM registration_keys WHERE key_value = %s", (key_value,), fetch=True, dict_cursor=True)
    return rows[0] if rows else None

def mark_key_as_bound_and_used(key_value, user_id, user_db_id):
    """
    Helper to set allowed_telegram_user_id (if null) and mark used/used_by fields.
    """
    return execute_query(
        "UPDATE registration_keys SET used = TRUE, used_by = %s, used_at = NOW(), allowed_telegram_user_id = %s WHERE key_value = %s",
        (user_db_id, user_id, key_value)
    )

# Users operations
def get_users():
    return execute_query(
        "SELECT u.*, rk.duration_months FROM users u LEFT JOIN registration_keys rk ON u.registration_key = rk.key_value ORDER BY u.created_at DESC",
        fetch=True,
        dict_cursor=True
    )

def get_user_by_telegram_id(telegram_user_id):
    rows = execute_query("SELECT * FROM users WHERE telegram_user_id = %s", (telegram_user_id,), fetch=True, dict_cursor=True)
    return rows[0] if rows else None

def create_or_update_user_by_telegram_id(telegram_user_id, key_value, expiry_date):
    """
    Insert or update user row using ON CONFLICT on telegram_user_id.
    Returns the user's DB id.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_user_id, registration_key, expiry_date)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE
            SET registration_key = EXCLUDED.registration_key,
                expiry_date = EXCLUDED.expiry_date,
                updated_at = NOW(),
                is_active = TRUE
            RETURNING id
        """, (telegram_user_id, key_value, expiry_date))
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return user_id
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: create_or_update_user_by_telegram_id failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

def redeem_registration_key(key_value, telegram_user_id):
    """
    Redeem a registration key by binding it to telegram_user_id and creating/updating the user.
    Returns a dict with success and expiry_date on success or error message on failure.
    """
    # Fetch key info
    rk = get_registration_key_by_value(key_value)
    if not rk:
        return {"success": False, "error": "Key not found"}

    if rk.get('used'):
        return {"success": False, "error": "Key already used"}

    allowed_id = rk.get('allowed_telegram_user_id')
    duration = rk.get('duration_months', 1)

    # If the key is bound to another telegram id -> reject
    if allowed_id and int(allowed_id) != int(telegram_user_id):
        return {"success": False, "error": "This key is reserved for a different Telegram user"}

    # Calculate expiry date
    expiry_date = datetime.utcnow() + timedelta(days=30 * int(duration))

    # Create or update user in users table
    try:
        user_db_id = create_or_update_user_by_telegram_id(telegram_user_id, key_value, expiry_date)
    except Exception as e:
        return {"success": False, "error": f"Failed to create user: {e}"}

    # Mark key as used, bind it to the telegram id
    try:
        mark_key_as_bound_and_used(key_value, telegram_user_id, user_db_id)
    except Exception as e:
        return {"success": False, "error": f"Failed to mark key used: {e}"}

    return {"success": True, "expiry_date": expiry_date.isoformat(), "user_id": user_db_id}
