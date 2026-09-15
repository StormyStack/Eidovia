DROP TABLE IF EXISTS ai_decision_log CASCADE;
DROP TABLE IF EXISTS rl_episodes CASCADE;
DROP TABLE IF EXISTS curriculum_chunks CASCADE;
DROP TABLE IF EXISTS experiments CASCADE;
DROP TABLE IF EXISTS interaction_events CASCADE;
DROP TABLE IF EXISTS user_profiles CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_questions INT DEFAULT 0,
    accuracy FLOAT DEFAULT 0.0
);

CREATE TABLE interaction_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    session_id UUID NOT NULL REFERENCES sessions(session_id),
    question VARCHAR(1000),
    correct BOOLEAN,
    response_time_ms FLOAT,
    server_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(user_id),
    accuracy FLOAT DEFAULT 0.5,
    difficulty_level INT DEFAULT 1
);

CREATE TABLE ai_decision_log (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id),
    session_id UUID REFERENCES sessions(session_id),
    question VARCHAR(1000),
    is_on_topic BOOLEAN,
    llm_response TEXT,
    latency_ms FLOAT,
    reward FLOAT DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rl_episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id),
    action_id INT,
    reward FLOAT
);

CREATE TABLE curriculum_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic VARCHAR(255),
    content TEXT,
    embedding FLOAT8[]
);

CREATE TABLE experiments (
    experiment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_name VARCHAR(255),
    baseline_accuracy FLOAT,
    adaptive_accuracy FLOAT
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_events_user ON interaction_events(user_id);
CREATE INDEX idx_decision_user ON ai_decision_log(user_id);
CREATE INDEX idx_chunks_topic ON curriculum_chunks(topic);

\dt