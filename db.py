import os
import psycopg2

def get_db_connection():
    """
    Return a new psycopg2 connection using the DATABASE_URL env var.
    """
    db_url = os.getenv('DATABASE_URL')
    print(f"DEBUG: DATABASE_URL is '{db_url}'")
    try:
        conn = psycopg2.connect(db_url)
        print("DEBUG: Successfully connected to the database.")
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to the database: {e}")
        raise

def init_db():
    """
    Create the required tables if they don't exist.
    Safe to call at startup.
    """
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
