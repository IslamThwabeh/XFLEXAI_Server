# database/operations.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

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
def create_registration_key(key_value, duration_months, created_by):
    return execute_query(
        "INSERT INTO registration_keys (key_value, duration_months, created_by) VALUES (%s, %s, %s)",
        (key_value, duration_months, created_by)
    )

def get_registration_keys():
    return execute_query(
        "SELECT rk.*, a.username as created_by_username FROM registration_keys rk LEFT JOIN admins a ON rk.created_by = a.id ORDER BY rk.created_at DESC",
        fetch=True,
        dict_cursor=True
    )

def get_users():
    return execute_query(
        "SELECT u.*, rk.duration_months FROM users u LEFT JOIN registration_keys rk ON u.registration_key = rk.key_value ORDER BY u.created_at DESC",
        fetch=True,
        dict_cursor=True
    )

def get_registration_key_by_value(key_value):
    rows = execute_query("SELECT * FROM registration_keys WHERE key_value = %s", (key_value,), fetch=True)
    return rows[0] if rows else None
