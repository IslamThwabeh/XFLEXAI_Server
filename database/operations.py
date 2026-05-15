# database/operations.py
import psycopg2
import json
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import datetime, timedelta
from utils.key_helpers import normalize_registration_key

INIT_DATABASE_LOCK_ID = 2147480361

def get_db_connection():
    db_url = Config.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured in environment")
    return psycopg2.connect(db_url)

def init_database():
    from database.models import get_table_definitions
    print("DEBUG: Starting database initialization (init_database).")
    conn = None
    cur = None
    lock_acquired = False
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_lock(%s)", (INIT_DATABASE_LOCK_ID,))
        lock_acquired = True
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
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analysis_sessions_updated_at ON analysis_sessions (updated_at);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_openai_usage_events_created_at ON openai_usage_events (created_at DESC);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_openai_usage_events_telegram_user_id ON openai_usage_events (telegram_user_id, created_at DESC);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_openai_usage_events_flow_id ON openai_usage_events (flow_id);
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

        conn.commit()
        print("DEBUG: Core database tables and indexes created/ensured.")

        def ensure_fk_constraint(constraint_name, alter_sql, success_message, exists_message):
            cur.execute("SELECT 1 FROM pg_constraint WHERE conname = %s", (constraint_name,))
            if cur.fetchone():
                print(f"DEBUG: {exists_message}")
                return

            try:
                cur.execute(alter_sql)
                conn.commit()
                print(f"DEBUG: {success_message}")
            except Exception as e:
                conn.rollback()
                print(f"DEBUG: Could not add {constraint_name}: {e}")

        # Add circular foreign keys after the core schema is committed so an existing
        # constraint cannot roll back newly created tables or indexes.
        ensure_fk_constraint(
            'fk_registration_keys_used_by',
            """
                ALTER TABLE registration_keys
                ADD CONSTRAINT fk_registration_keys_used_by
                FOREIGN KEY (used_by) REFERENCES users(id)
            """,
            'Added FK registration_keys.used_by -> users.id',
            'FK registration_keys.used_by -> users.id already exists'
        )

        ensure_fk_constraint(
            'fk_users_registration_key_id',
            """
                ALTER TABLE users
                ADD CONSTRAINT fk_users_registration_key_id
                FOREIGN KEY (registration_key_id) REFERENCES registration_keys(id)
            """,
            'Added FK users.registration_key_id -> registration_keys.id',
            'FK users.registration_key_id -> registration_keys.id already exists'
        )

        print("DEBUG: Database tables created/ensured.")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: init_database failed: {e}")
        raise
    finally:
        if conn:
            if cur and lock_acquired:
                try:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (INIT_DATABASE_LOCK_ID,))
                    conn.commit()
                except Exception as unlock_error:
                    print(f"DEBUG: Failed to release init_database advisory lock cleanly: {unlock_error}")
                    conn.rollback()
            if cur:
                cur.close()
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

def get_analysis_session(telegram_user_id):
    rows = execute_query(
        "SELECT telegram_user_id, session_data, status, updated_at FROM analysis_sessions WHERE telegram_user_id = %s",
        (telegram_user_id,),
        fetch=True,
        dict_cursor=True
    )
    if not rows:
        return None

    row = dict(rows[0])
    session_data = row.get('session_data')
    if isinstance(session_data, str):
        try:
            session_data = json.loads(session_data)
        except json.JSONDecodeError:
            session_data = {}

    row['session_data'] = session_data or {}
    return row

def upsert_analysis_session(telegram_user_id, session_data):
    payload = json.dumps(session_data, ensure_ascii=False)
    execute_query(
        """
        INSERT INTO analysis_sessions (telegram_user_id, session_data, status, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (telegram_user_id) DO UPDATE
        SET session_data = EXCLUDED.session_data,
            status = EXCLUDED.status,
            updated_at = NOW()
        """,
        (telegram_user_id, payload, session_data.get('status', 'ready'))
    )

def delete_analysis_session(telegram_user_id):
    execute_query("DELETE FROM analysis_sessions WHERE telegram_user_id = %s", (telegram_user_id,))

def clear_analysis_sessions():
    rows = execute_query(
        "DELETE FROM analysis_sessions RETURNING telegram_user_id",
        fetch=True,
        dict_cursor=True
    )
    return len(rows)

def count_analysis_sessions():
    rows = execute_query(
        "SELECT COUNT(*) AS session_count FROM analysis_sessions",
        fetch=True,
        dict_cursor=True
    )
    if not rows:
        return 0
    return int(rows[0].get('session_count', 0))

def create_openai_usage_event(event_data):
    payload = event_data or {}
    execute_query(
        """
        INSERT INTO openai_usage_events (
            telegram_user_id,
            endpoint_name,
            flow_type,
            flow_id,
            action_type,
            model_name,
            request_mode,
            image_detail,
            timeframe,
            currency_pair,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            estimated_cost_usd,
            success,
            error_message
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payload.get('telegram_user_id'),
            payload.get('endpoint_name'),
            payload.get('flow_type'),
            payload.get('flow_id'),
            payload.get('action_type'),
            payload.get('model_name'),
            payload.get('request_mode', 'text'),
            payload.get('image_detail'),
            payload.get('timeframe'),
            payload.get('currency_pair'),
            int(payload.get('prompt_tokens') or 0),
            int(payload.get('completion_tokens') or 0),
            int(payload.get('total_tokens') or 0),
            float(payload.get('estimated_cost_usd') or 0),
            bool(payload.get('success', True)),
            payload.get('error_message')
        )
    )

def get_openai_usage_summary(days=7):
    normalized_days = max(1, int(days or 7))
    rows = execute_query(
        """
        SELECT
            COALESCE(SUM(CASE WHEN created_at >= CURRENT_DATE THEN estimated_cost_usd ELSE 0 END), 0) AS today_cost,
            COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today_calls,
            COUNT(DISTINCT telegram_user_id) FILTER (
                WHERE created_at >= CURRENT_DATE AND telegram_user_id IS NOT NULL
            ) AS today_users,
            COALESCE(SUM(CASE WHEN created_at >= NOW() - (%s::int * INTERVAL '1 day') THEN estimated_cost_usd ELSE 0 END), 0) AS period_cost,
            COUNT(*) FILTER (WHERE created_at >= NOW() - (%s::int * INTERVAL '1 day')) AS period_calls,
            COUNT(DISTINCT telegram_user_id) FILTER (
                WHERE created_at >= NOW() - (%s::int * INTERVAL '1 day') AND telegram_user_id IS NOT NULL
            ) AS period_users
        FROM openai_usage_events
        """,
        (normalized_days, normalized_days, normalized_days),
        fetch=True,
        dict_cursor=True
    )
    summary = rows[0] if rows else {}
    return {
        'today_cost': float(summary.get('today_cost', 0) or 0),
        'today_calls': int(summary.get('today_calls', 0) or 0),
        'today_users': int(summary.get('today_users', 0) or 0),
        'period_cost': float(summary.get('period_cost', 0) or 0),
        'period_calls': int(summary.get('period_calls', 0) or 0),
        'period_users': int(summary.get('period_users', 0) or 0)
    }

def get_openai_user_daily_usage(days=7, limit=100):
    normalized_days = max(1, int(days or 7))
    normalized_limit = max(1, int(limit or 100))
    rows = execute_query(
        """
        SELECT
            DATE(created_at) AS usage_day,
            telegram_user_id,
            COUNT(*) AS call_count,
            COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
            MAX(created_at) AS last_request_at
        FROM openai_usage_events
        WHERE created_at >= NOW() - (%s::int * INTERVAL '1 day')
          AND telegram_user_id IS NOT NULL
        GROUP BY DATE(created_at), telegram_user_id
        ORDER BY usage_day DESC, estimated_cost_usd DESC, call_count DESC
        LIMIT %s
        """,
        (normalized_days, normalized_limit),
        fetch=True,
        dict_cursor=True
    )

    usage_rows = []
    for row in rows or []:
        usage_rows.append({
            'usage_day': row.get('usage_day'),
            'telegram_user_id': row.get('telegram_user_id'),
            'call_count': int(row.get('call_count', 0) or 0),
            'prompt_tokens': int(row.get('prompt_tokens', 0) or 0),
            'completion_tokens': int(row.get('completion_tokens', 0) or 0),
            'total_tokens': int(row.get('total_tokens', 0) or 0),
            'estimated_cost_usd': float(row.get('estimated_cost_usd', 0) or 0),
            'last_request_at': row.get('last_request_at')
        })
    return usage_rows

def get_openai_action_breakdown(days=7, limit=20):
    normalized_days = max(1, int(days or 7))
    normalized_limit = max(1, int(limit or 20))
    rows = execute_query(
        """
        SELECT
            action_type,
            model_name,
            request_mode,
            COUNT(*) AS call_count,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
        FROM openai_usage_events
        WHERE created_at >= NOW() - (%s::int * INTERVAL '1 day')
        GROUP BY action_type, model_name, request_mode
        ORDER BY estimated_cost_usd DESC, call_count DESC
        LIMIT %s
        """,
        (normalized_days, normalized_limit),
        fetch=True,
        dict_cursor=True
    )

    breakdown_rows = []
    for row in rows or []:
        breakdown_rows.append({
            'action_type': row.get('action_type'),
            'model_name': row.get('model_name'),
            'request_mode': row.get('request_mode'),
            'call_count': int(row.get('call_count', 0) or 0),
            'total_tokens': int(row.get('total_tokens', 0) or 0),
            'estimated_cost_usd': float(row.get('estimated_cost_usd', 0) or 0)
        })
    return breakdown_rows

# Admin operations
def get_admin_by_username(username):
    rows = execute_query(
        "SELECT * FROM admins WHERE username = %s AND is_deleted = FALSE",
        (username,),
        fetch=True,
        dict_cursor=True
    )
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
    key_value = normalize_registration_key(key_value)
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

def deactivate_registration_key(key_value):
    normalized_key = normalize_registration_key(key_value)
    if not normalized_key:
        return None

    rows = execute_query(
        """
        UPDATE registration_keys
        SET is_active = FALSE
        WHERE key_value = %s AND is_deleted = FALSE
        RETURNING id, key_value, is_active
        """,
        (normalized_key,),
        fetch=True,
        dict_cursor=True
    )
    return rows[0] if rows else None

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
        key_value = normalize_registration_key(key_value)
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

        # If key is already used, check if it was used by the current user
        if rk.get('used'):
            # Fetch the user who used this key
            cur.execute("SELECT * FROM users WHERE id = %s", (rk.get('used_by'),))
            existing_user = cur.fetchone()
            
            if existing_user and int(existing_user.get('telegram_user_id')) == int(telegram_user_id):
                # Same user redeeming the same key again -> return success with current expiry
                cur.close()
                conn.rollback()
                expiry_date = existing_user.get('expiry_date')
                return {"success": True, "expiry_date": expiry_date.isoformat() if isinstance(expiry_date, datetime) else expiry_date, "user_id": existing_user.get('id'), "message": "Key already redeemed"}
            else:
                # Different user trying to use this key -> error
                cur.close()
                conn.rollback()
                return {"success": False, "error": "Key already used by another user"}

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
