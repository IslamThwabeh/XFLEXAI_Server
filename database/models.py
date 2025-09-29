# database/models.py
# Provides DDL statements for new canonical schema.

def get_table_definitions():
    return {
        'key_types': '''
            CREATE TABLE IF NOT EXISTS key_types (
              id SERIAL PRIMARY KEY,
              name VARCHAR(50) NOT NULL,
              duration_months INTEGER NOT NULL,
              description TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''',
        'admins': '''
            CREATE TABLE IF NOT EXISTS admins (
              id SERIAL PRIMARY KEY,
              username VARCHAR(50) UNIQUE NOT NULL,
              password_hash VARCHAR(255) NOT NULL,
              is_active BOOLEAN DEFAULT TRUE,
              is_deleted BOOLEAN DEFAULT FALSE,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''',
        'registration_keys': '''
            CREATE TABLE IF NOT EXISTS registration_keys (
              id SERIAL PRIMARY KEY,
              key_value VARCHAR(32) UNIQUE NOT NULL,
              key_type_id INTEGER REFERENCES key_types(id) ON DELETE SET NULL,
              duration_months INTEGER NOT NULL DEFAULT 1,
              created_by INTEGER REFERENCES admins(id),
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              allowed_telegram_user_id BIGINT,
              used BOOLEAN DEFAULT FALSE,
              used_by INTEGER REFERENCES users(id),
              used_at TIMESTAMP,
              is_active BOOLEAN DEFAULT TRUE,
              is_deleted BOOLEAN DEFAULT FALSE,
              notes TEXT
            )
        ''',
        'users': '''
            CREATE TABLE IF NOT EXISTS users (
              id SERIAL PRIMARY KEY,
              telegram_user_id BIGINT UNIQUE NOT NULL,
              registration_key_id INTEGER REFERENCES registration_keys(id),
              registration_key_value VARCHAR(32),
              expiry_date TIMESTAMP NOT NULL,
              is_active BOOLEAN DEFAULT TRUE,
              is_deleted BOOLEAN DEFAULT FALSE,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''
    }
