-- Reference schema for the ORM-backed content store.
-- Runtime migrations are applied by services/content-store/app/main.py.
CREATE TABLE IF NOT EXISTS content_candidates (
    id BIGSERIAL PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    client_id TEXT NOT NULL DEFAULT 'telegram-default',
    source TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_published_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    source_text TEXT,
    relevant BOOLEAN NOT NULL DEFAULT FALSE,
    confidence NUMERIC(5, 4),
    quality_score NUMERIC(5, 4),
    draft_title TEXT,
    draft_text TEXT,
    final_title TEXT,
    final_text TEXT,
    reason TEXT,
    risks JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggested_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'processing',
    processing_started_at TIMESTAMPTZ,
    processing_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    moderated_at TIMESTAMPTZ,
    channel_published_at TIMESTAMPTZ,
    published_message_id BIGINT,
    published_chat_id BIGINT,
    ai_model TEXT,
    raw_analysis JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_content_candidates_status ON content_candidates(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_candidates_source_url ON content_candidates(source_url);
CREATE INDEX IF NOT EXISTS idx_content_candidates_processing ON content_candidates(status, next_retry_at);

CREATE TABLE IF NOT EXISTS moderation_events (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT NOT NULL,
    moderator_id BIGINT,
    action TEXT NOT NULL,
    reject_reason TEXT,
    original_title TEXT,
    original_text TEXT,
    edited_title TEXT,
    edited_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_moderation_events_candidate ON moderation_events(candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS client_style_profiles (
    client_id TEXT PRIMARY KEY,
    client_name TEXT,
    profile_text TEXT,
    rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS style_review_predictions (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT NOT NULL,
    client_id TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'low',
    confidence NUMERIC(5, 4) NOT NULL DEFAULT 0,
    likely_edits JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary TEXT NOT NULL DEFAULT '',
    ai_model TEXT NOT NULL DEFAULT 'local-main',
    raw_review JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_style_review_predictions_candidate ON style_review_predictions(candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_metric_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    candidate_id BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_metric_events_type ON pipeline_metric_events(event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_error_events (
    id BIGSERIAL PRIMARY KEY,
    workflow_name TEXT,
    node_name TEXT,
    execution_id TEXT,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
