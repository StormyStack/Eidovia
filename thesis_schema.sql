CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- SKIP: CREATE EXTENSION IF NOT EXISTS vector;  ← Comment out

CREATE TABLE IF NOT EXISTS users (
    user_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    detail_level  INT NOT NULL DEFAULT 1,
    language      TEXT NOT NULL DEFAULT 'en',
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(user_id),
    started_at  TIMESTAMPTZ DEFAULT now(),
    ended_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS events (
    event_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID NOT NULL REFERENCES users(user_id),
    session_id       UUID NOT NULL REFERENCES sessions(session_id),
    scene_name       TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    object_id        TEXT,
    module_id        TEXT,
    correct          BOOLEAN,
    time_spent_ms    INT,
    payload          JSONB DEFAULT '{}',
    client_timestamp TIMESTAMPTZ NOT NULL,
    server_timestamp TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_events_session ON events(session_id, scene_name);

CREATE TABLE IF NOT EXISTS modules (
    module_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    scene_name     TEXT NOT NULL,
    cdn_bundle_url TEXT NOT NULL,
    difficulty     INT DEFAULT 1,
    config         JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_id   TEXT NOT NULL,
    source_doc  TEXT NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   FLOAT8[],  -- Use array instead of VECTOR
    created_at  TIMESTAMPTZ DEFAULT now()
);
-- Skip ivfflat index, use Python for similarity search

INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url, difficulty, config)
VALUES (
    'dna-01', 'DNA Structure Module', 'DNAScene_Main',
    'https://cdn.example.com/dna_module.bundle', 1,
    '{"hint_color": "#00FFFF", "speed": 1.0}'
) ON CONFLICT (module_id) DO NOTHING;