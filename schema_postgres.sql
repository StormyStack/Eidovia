-- thesis_db schema
-- AI Engineer: Shabab
-- Date: September 2026
-- Purpose: Scalable data storage for adaptive learning system

-- ============================================================
-- CORE TABLES
-- ============================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    duration_seconds INT,
    total_questions INT DEFAULT 0,
    correct_answers INT DEFAULT 0,
    accuracy FLOAT DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Interaction events table (raw data collection)
CREATE TABLE IF NOT EXISTS interaction_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- quiz_answer, ar_interaction, hint_requested, content_viewed
    question_id VARCHAR(255),
    topic VARCHAR(255),
    difficulty INT DEFAULT 1,
    correct BOOLEAN,
    response_time_ms FLOAT,
    payload JSONB, -- flexible data for different event types
    client_timestamp TIMESTAMP,
    server_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_session (user_id, session_id),
    INDEX idx_event_type (event_type),
    INDEX idx_timestamp (server_timestamp)
);

-- User profiles table (current state)
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    -- 8D state vector
    accuracy FLOAT DEFAULT 0.5,
    response_time_ms FLOAT DEFAULT 3000.0,
    difficulty_level INT DEFAULT 1,
    topic_match FLOAT DEFAULT 0.5,
    engagement FLOAT DEFAULT 0.5,
    question_count INT DEFAULT 0,
    error_rate FLOAT DEFAULT 0.5,
    time_spent_minutes FLOAT DEFAULT 0.0,
    -- Metadata
    preferred_difficulty INT DEFAULT 1,
    preferred_topic VARCHAR(255) DEFAULT 'DNA Structure',
    engagement_streak INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id)
);

-- AI decision log table (audit trail)
CREATE TABLE IF NOT EXISTS ai_decision_log (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    question VARCHAR(1000),
    is_on_topic BOOLEAN,
    topic_similarity FLOAT,
    retrieved_chunks INT DEFAULT 0,
    llm_response TEXT,
    llm_confidence FLOAT,
    latency_ms FLOAT,
    action_id INT,
    action_name VARCHAR(100),
    recommended_difficulty INT,
    recommended_topic VARCHAR(255),
    reward FLOAT DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_session (user_id, session_id),
    INDEX idx_timestamp (created_at)
);

-- RL episodes table (training data)
CREATE TABLE IF NOT EXISTS rl_episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    state_vector FLOAT8[], -- 8D state
    action_id INT,
    reward FLOAT,
    next_state_vector FLOAT8[],
    done BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_episode (episode_id)
);

-- Curriculum chunks table (knowledge base)
CREATE TABLE IF NOT EXISTS curriculum_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding FLOAT8[], -- embedding vector (384-dim for all-MiniLM-L6-v2)
    embedding_dim INT DEFAULT 384,
    source VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_topic (topic),
    INDEX idx_chunk_id (chunk_id)
);

-- Experiment tracking table (MLflow integration)
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_name VARCHAR(255) NOT NULL,
    description TEXT,
    baseline_accuracy FLOAT,
    adaptive_accuracy FLOAT,
    improvement_percent FLOAT,
    num_users INT,
    num_interactions INT,
    avg_latency_ms FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    notes TEXT,
    INDEX idx_name (experiment_name)
);

-- ============================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_events_user ON interaction_events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON interaction_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON interaction_events(server_timestamp);
CREATE INDEX IF NOT EXISTS idx_decision_user ON ai_decision_log(user_id);
CREATE INDEX IF NOT EXISTS idx_decision_timestamp ON ai_decision_log(created_at);
CREATE INDEX IF NOT EXISTS idx_episodes_user ON rl_episodes(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_topic ON curriculum_chunks(topic);

-- ============================================================
-- VIEWS FOR ANALYSIS
-- ============================================================

-- User learning progress view
CREATE OR REPLACE VIEW user_learning_progress AS
SELECT 
    u.user_id,
    u.username,
    COUNT(DISTINCT s.session_id) as total_sessions,
    COUNT(DISTINCT ie.event_id) as total_interactions,
    SUM(CASE WHEN ie.correct THEN 1 ELSE 0 END)::FLOAT / COUNT(ie.event_id) as overall_accuracy,
    AVG(ie.response_time_ms) as avg_response_time,
    COUNT(DISTINCT ie.topic) as topics_covered,
    MAX(s.created_at) as last_session
FROM users u
LEFT JOIN sessions s ON u.user_id = s.user_id
LEFT JOIN interaction_events ie ON s.session_id = ie.session_id
GROUP BY u.user_id, u.username;

-- Bandit performance view
CREATE OR REPLACE VIEW bandit_action_performance AS
SELECT 
    action_id,
    action_name,
    COUNT(*) as action_count,
    AVG(reward) as avg_reward,
    COUNT(*) FILTER (WHERE reward > 0.5) as successful_actions,
    (COUNT(*) FILTER (WHERE reward > 0.5)::FLOAT / COUNT(*)) as success_rate
FROM ai_decision_log
WHERE action_id IS NOT NULL
GROUP BY action_id, action_name
ORDER BY success_rate DESC;

-- ============================================================
-- STORED PROCEDURES
-- ============================================================

-- Update user profile based on latest interactions
CREATE OR REPLACE FUNCTION update_user_profile(p_user_id UUID)
RETURNS void AS $$
BEGIN
    UPDATE user_profiles
    SET
        accuracy = COALESCE(
            (SELECT SUM(CASE WHEN correct THEN 1 ELSE 0 END)::FLOAT / COUNT(*) 
             FROM interaction_events 
             WHERE user_id = p_user_id AND server_timestamp > CURRENT_TIMESTAMP - INTERVAL '10 questions'),
            0.5
        ),
        question_count = (
            SELECT COUNT(*) FROM interaction_events WHERE user_id = p_user_id
        ),
        error_rate = 1.0 - COALESCE(
            (SELECT SUM(CASE WHEN correct THEN 1 ELSE 0 END)::FLOAT / COUNT(*) 
             FROM interaction_events 
             WHERE user_id = p_user_id AND server_timestamp > CURRENT_TIMESTAMP - INTERVAL '10 questions'),
            0.5
        ),
        last_updated = CURRENT_TIMESTAMP
    WHERE user_id = p_user_id;
END;
$$ LANGUAGE plpgsql;

-- Log AI decision
CREATE OR REPLACE FUNCTION log_ai_decision(
    p_user_id UUID,
    p_session_id UUID,
    p_question VARCHAR,
    p_is_on_topic BOOLEAN,
    p_topic_similarity FLOAT,
    p_retrieved_chunks INT,
    p_llm_response TEXT,
    p_llm_confidence FLOAT,
    p_latency_ms FLOAT,
    p_action_id INT,
    p_action_name VARCHAR,
    p_recommended_difficulty INT,
    p_recommended_topic VARCHAR,
    p_reward FLOAT
)
RETURNS UUID AS $$
DECLARE
    v_decision_id UUID;
BEGIN
    INSERT INTO ai_decision_log (
        user_id, session_id, question, is_on_topic, topic_similarity,
        retrieved_chunks, llm_response, llm_confidence, latency_ms,
        action_id, action_name, recommended_difficulty, recommended_topic, reward
    ) VALUES (
        p_user_id, p_session_id, p_question, p_is_on_topic, p_topic_similarity,
        p_retrieved_chunks, p_llm_response, p_llm_confidence, p_latency_ms,
        p_action_id, p_action_name, p_recommended_difficulty, p_recommended_topic, p_reward
    ) RETURNING decision_id INTO v_decision_id;
    
    RETURN v_decision_id;
END;
$$ LANGUAGE plpgsql;

COMMIT;
