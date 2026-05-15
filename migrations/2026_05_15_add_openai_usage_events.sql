BEGIN;

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
);

CREATE INDEX IF NOT EXISTS idx_openai_usage_events_created_at
  ON openai_usage_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_openai_usage_events_telegram_user_id
  ON openai_usage_events (telegram_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_openai_usage_events_flow_id
  ON openai_usage_events (flow_id);

COMMIT;
