-- EduAR-AI storage schema
-- Auto-executed once, on first container start (empty pgdata volume only).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ==========================================================
-- 1. Learner Identity & Pedagogical Profile
-- ==========================================================
CREATE TABLE IF NOT EXISTS users (
    user_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    detail_level  INT NOT NULL DEFAULT 1,
    language      TEXT NOT NULL DEFAULT 'en',
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- 2. Educational Learning Sessions
-- ==========================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    started_at  TIMESTAMPTZ DEFAULT now(),
    ended_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

-- ==========================================================
-- 3. High-Frequency Interaction & Telemetry Stream
-- ==========================================================
CREATE TABLE IF NOT EXISTS events (
    event_id         UUID PRIMARY KEY,
    user_id          UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id       UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    scene_name       TEXT NOT NULL,
    event_type       TEXT NOT NULL,          -- 'ar_interaction' | 'quiz_answer' | 'hint_requested' | 'content_skip'
    object_id        TEXT,
    module_id        TEXT,
    correct          BOOLEAN,
    time_spent_ms    INT,
    payload          JSONB DEFAULT '{}',
    client_timestamp TIMESTAMPTZ NOT NULL,
    server_timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_server_timestamp ON events(server_timestamp);

-- ==========================================================
-- 4. Pedagogical Curricular Modules & Scene Binding
-- ==========================================================
CREATE TABLE IF NOT EXISTS modules (
    module_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    scene_name     TEXT NOT NULL,
    cdn_bundle_url TEXT NOT NULL,
    difficulty     INT NOT NULL DEFAULT 1,
    config         JSONB DEFAULT '{}'
);

-- ==========================================================
-- 5. RAG Vector Knowledge Store (384-dimensional embeddings)
-- ==========================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_id  TEXT REFERENCES modules(module_id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    embedding  vector(384) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Optimized IVFFlat cosine similarity index for sub-45ms retrieval
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
