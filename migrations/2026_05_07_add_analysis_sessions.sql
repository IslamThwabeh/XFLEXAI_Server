BEGIN;

CREATE TABLE IF NOT EXISTS analysis_sessions (
  telegram_user_id BIGINT PRIMARY KEY,
  session_data TEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ready',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_sessions_updated_at ON analysis_sessions (updated_at);

COMMIT;