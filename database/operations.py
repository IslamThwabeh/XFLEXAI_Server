# database/operations.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import datetime, timedelta

def get_db_connection():
    db_url = Config.DATABASE_URL
    print(f"DEBUG: DATABASE_URL (from config) is '{db_url}'")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured in environment")
    return psycopg2.connect(db_url)

def init_database():
    from database.models import get_table_definitions
    print("DEBUG: Starting database initialization (init_database).")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        tables = get_table_definitions()
        # Create each table (no circular FKs in DDL)
        for name, ddl in tables.items():
            cur.execute(ddl)
            print(f"DEBUG: Ensured table {name}")

        # ensure indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id ON users (telegram_user_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_registration_keys_key_value ON registration_keys (key_value);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_registration_keys_allowed_telegram_user_id ON registration_keys (allowed_telegram_user_id);
        """)

        # Seed basic key_types if not present
        cur.execute("""
            INSERT INTO key_types (name, duration_months, description)
            SELECT v.name, v.duration_months, v.description
            FROM (VALUES
              ('1-month', 1, '1 month license'),
              ('3-month', 3, '3 months license'),
              ('12-month', 12, '1 year license')
            ) AS v(name, duration_months, description)
            WHERE NOT EXISTS (SELECT 1 FROM key_types WHERE name = v.name)
        """)

        # Now add the FK constraints that reference the other table.
        # Wrap each ALTER in try/except so init_database is idempotent and won't fail
        # if the constraint already exists or if something else prevents adding it.
        try:
            cur.execute("""
                ALTER TABLE registration_keys
                ADD CONSTRAINT fk_registration_keys_used_by
                FOREIGN KEY (used_by) REFERENCES users(id)
            """)
            print("DEBUG: Added FK registration_keys.used_by -> users.id")
        except Exception as e:
            print(f"DEBUG: Could not add FK registration_keys.used_by -> users.id (may already exist): {e}")

        try:
            cur.execute("""
                ALTER TABLE users
                ADD CONSTRAINT fk_users_registration_key_id
                FOREIGN KEY (registration_key_id) REFERENCES registration_keys(id)
            """)
            print("DEBUG: Added FK users.registration_key_id -> registration_keys.id")
        except Exception as e:
            print(f"DEBUG: Could not add FK users.registration_key_id -> registration_keys.id (may already exist): {e}")

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
    rows = execute_query("SELECT * FROM admins WHERE username = %s AND is_deleted = FALSE", (username,), fetch=True)
    return rows[0] if rows else None

def create_admin(username, password_hash):
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

# Key operations
def create_registration_key(key_value, duration_months, created_by, allowed_telegram_user_id=None, key_type_id=None, notes=None):
    return execute_query(
        "INSERT INTO registration_keys (key_value, duration_months, created_by, allowed_telegram_user_id, key_type_id, notes) VALUES (%s, %s, %s, %s, %s, %s)",
        (key_value, duration_months, created_by, allowed_telegram_user_id, key_type_id, notes)
    )

def get_registration_keys():
    return execute_query(
        """
        SELECT rk.id, rk.key_value, rk.duration_months, rk.allowed_telegram_user_id,
               rk.used, rk.used_by, rk.used_at, rk.created_at, rk.is_active, rk.is_deleted,
               kt.name as key_type_name, a.username as created_by_username, u.telegram_user_id as used_by_telegram
        FROM registration_keys rk
        LEFT JOIN key_types kt ON rk.key_type_id = kt.id
        LEFT JOIN admins a ON rk.created_by = a.id
        LEFT JOIN users u ON rk.used_by = u.id
        WHERE rk.is_deleted = FALSE
        ORDER BY rk.created_at DESC
        """,
        fetch=True,
        dict_cursor=True
    )

# User operations
def get_users():
    return execute_query(
        """
        SELECT u.id, u.telegram_user_id, u.registration_key_id, u.registration_key_value, u.expiry_date, u.is_active, u.is_deleted, u.created_at
        FROM users u
        WHERE u.is_deleted = FALSE
        ORDER BY u.created_at DESC
        """,
        fetch=True,
        dict_cursor=True
    )

def get_user_by_telegram_id(telegram_user_id):
    rows = execute_query("SELECT * FROM users WHERE telegram_user_id = %s AND is_deleted = FALSE", (telegram_user_id,), fetch=True, dict_cursor=True)
    return rows[0] if rows else None

def create_or_update_user_by_telegram_id(telegram_user_id, key_id, key_value, expiry_date):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_user_id, registration_key_id, registration_key_value, expiry_date)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE
            SET registration_key_id = EXCLUDED.registration_key_id,
                registration_key_value = EXCLUDED.registration_key_value,
                expiry_date = EXCLUDED.expiry_date,
                updated_at = NOW(),
                is_active = TRUE
            RETURNING id
        """, (telegram_user_id, key_id, key_value, expiry_date))
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

# Redeem flow (transactional)
def redeem_registration_key(key_value, telegram_user_id):
    """
    Redeem a registration key:
    - ensure key exists, is_active, not used
    - ensure allowed_telegram_user_id is null or matches telegram_user_id
    - create/update users row and mark key as used and bound
    Returns dict with success and expiry_date iso string on success, or error.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Lock the key row to avoid races
        cur.execute("SELECT * FROM registration_keys WHERE key_value = %s FOR UPDATE", (key_value,))
        rk = cur.fetchone()
        if not rk:
            cur.close()
            conn.rollback()
            return {"success": False, "error": "Key not found"}

        if rk.get('is_deleted'):
            cur.close()
            conn.rollback()
            return {"success": False, "error": "Key is deleted"}

        if not rk.get('is_active'):
            cur.close()
            conn.rollback()
            return {"success": False, "error": "Key is not active"}

        if rk.get('used'):
            cur.close()
            conn.rollback()
            return {"success": False, "error": "Key already used"}

        allowed = rk.get('allowed_telegram_user_id')
        if allowed and int(allowed) != int(telegram_user_id):
            cur.close()
            conn.rollback()
            return {"success": False, "error": "This key is reserved for a different Telegram user"}

        # compute expiry
        duration = rk.get('duration_months') or 1
        expiry_date = datetime.utcnow() + timedelta(days=30 * int(duration))

        # create/update user
        # Use direct SQL here to reuse same connection/transaction
        cur.execute("""
            INSERT INTO users (telegram_user_id, registration_key_id, registration_key_value, expiry_date)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE
            SET registration_key_id = EXCLUDED.registration_key_id,
                registration_key_value = EXCLUDED.registration_key_value,
                expiry_date = EXCLUDED.expiry_date,
                updated_at = NOW(),
                is_active = TRUE
            RETURNING id
        """, (telegram_user_id, rk.get('id'), rk.get('key_value'), expiry_date))
        user_id = cur.fetchone()['id']

        # mark key used and bind allowed_telegram_user_id
        cur.execute("""
            UPDATE registration_keys
            SET used = TRUE, used_by = %s, used_at = NOW(), allowed_telegram_user_id = %s
            WHERE id = %s
        """, (user_id, telegram_user_id, rk.get('id')))

        conn.commit()
        cur.close()
        return {"success": True, "expiry_date": expiry_date.isoformat(), "user_id": user_id}
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: redeem_registration_key failed: {e}")
        raise
    finally:
        if conn:
            conn.close()
