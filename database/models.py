# database/models.py
# This file defines the SQL table creation statements.

def get_table_definitions():
    return {
        'admins': '''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''',
        'users': '''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_user_id BIGINT UNIQUE NOT NULL,
                registration_key VARCHAR(20) UNIQUE NOT NULL,
                expiry_date TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''',
        'registration_keys': '''
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
        '''
    }
