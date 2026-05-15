# database/models.py
# Provides DDL statements for canonical schema.
# Note: foreign-key constraints that reference the other table are added later
# via ALTER TABLE in init_database() to avoid circular creation issues.

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
        # create users WITHOUT a foreign-key to registration_keys (avoid circular FK)
        'users': '''
            CREATE TABLE IF NOT EXISTS users (
              id SERIAL PRIMARY KEY,
              telegram_user_id BIGINT UNIQUE NOT NULL,
              registration_key_id INTEGER,                 -- add FK later
              registration_key_value VARCHAR(32),
              expiry_date TIMESTAMP NOT NULL,
              is_active BOOLEAN DEFAULT TRUE,
              is_deleted BOOLEAN DEFAULT FALSE,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''',
        # create registration_keys WITHOUT a foreign-key to users (used_by FK added later)
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
              used_by INTEGER,      -- add FK later to users(id)
              used_at TIMESTAMP,
              is_active BOOLEAN DEFAULT TRUE,
              is_deleted BOOLEAN DEFAULT FALSE,
              notes TEXT
            )
        ''',
        'analysis_sessions': '''
            CREATE TABLE IF NOT EXISTS analysis_sessions (
              telegram_user_id BIGINT PRIMARY KEY,
              session_data TEXT NOT NULL,
              status VARCHAR(32) NOT NULL DEFAULT 'ready',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''',
        'openai_usage_events': '''
            CREATE TABLE IF NOT EXISTS openai_usage_events (
              id BIGSERIAL PRIMARY KEY,
              telegram_user_id BIGINT,
              endpoint_name VARCHAR(64),
              flow_type VARCHAR(64),
              flow_id VARCHAR(64),
              action_type VARCHAR(64) NOT NULL,
              model_name VARCHAR(64) NOT NULL,
              request_mode VARCHAR(16) NOT NULL DEFAULT 'text',
              image_detail VARCHAR(16),
              timeframe VARCHAR(32),
              currency_pair VARCHAR(32),
              prompt_tokens INTEGER NOT NULL DEFAULT 0,
              completion_tokens INTEGER NOT NULL DEFAULT 0,
              total_tokens INTEGER NOT NULL DEFAULT 0,
              estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
              success BOOLEAN NOT NULL DEFAULT TRUE,
              error_message TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''
    }
