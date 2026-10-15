-- ==========================================================
-- DNA quiz: versioned definitions, attempts, admin access requests, wildcard ledger, admin audit log,
-- and a ranking-ready per-user view. All additive (IF NOT EXISTS); nothing existing is changed.
-- The gateway runs the same statements on startup (app/quiz_service.py SCHEMA), so older databases
-- get them too. Raw attempts are the source of truth; the view is derived and always consistent.
-- ==========================================================

-- Quiz definitions. questions = what the app may see; answer_key = server only.
CREATE TABLE IF NOT EXISTS quiz_versions (
    quiz_id        TEXT NOT NULL,
    version        INT  NOT NULL CHECK (version > 0),
    title          TEXT NOT NULL,
    questions      JSONB NOT NULL,
    answer_key     JSONB NOT NULL,
    question_count INT  NOT NULL CHECK (question_count > 0),
    time_limit_s   INT  NOT NULL CHECK (time_limit_s > 0),
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (quiz_id, version)
);

-- "Let me take the quiz before my cooldown ends": pending -> approved | rejected; approved -> used | expired
CREATE TABLE IF NOT EXISTS quiz_access_requests (
    request_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    username        TEXT,
    quiz_id         TEXT NOT NULL DEFAULT 'dna',
    reason          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'used', 'expired')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at      TIMESTAMPTZ,
    decided_by      TEXT,
    decision_reason TEXT,
    window_start    TIMESTAMPTZ,
    window_end      TIMESTAMPTZ,
    cooldown_hours  INT CHECK (cooldown_hours IS NULL OR cooldown_hours BETWEEN 0 AND 168),
    used_at         TIMESTAMPTZ,
    used_attempt_id UUID,
    CHECK (status NOT IN ('approved', 'used') OR (window_start IS NOT NULL AND window_end > window_start))
);
-- one pending and at most one open (approved, not yet used) authorization per user
CREATE UNIQUE INDEX IF NOT EXISTS uq_quiz_request_pending  ON quiz_access_requests(user_id) WHERE status = 'pending';
CREATE UNIQUE INDEX IF NOT EXISTS uq_quiz_request_approved ON quiz_access_requests(user_id) WHERE status = 'approved';
CREATE INDEX IF NOT EXISTS idx_quiz_requests_status  ON quiz_access_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quiz_requests_user    ON quiz_access_requests(user_id, created_at DESC);

-- One row per attempt. Completed rows are the results; abandoned/expired rows are kept but never counted as results.
CREATE TABLE IF NOT EXISTS quiz_attempts (
    attempt_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT NOT NULL,
    username          TEXT,
    quiz_id           TEXT NOT NULL,
    quiz_version      INT  NOT NULL,
    attempt_type      TEXT NOT NULL CHECK (attempt_type IN ('normal', 'forced', 'authorized')),
    status            TEXT NOT NULL DEFAULT 'in_progress'
                      CHECK (status IN ('in_progress', 'completed', 'abandoned', 'expired')),
    start_key         TEXT NOT NULL,                   -- client idempotency key for "start"
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ NOT NULL,
    ended_at          TIMESTAMPTZ,
    cooldown_hours    INT NOT NULL DEFAULT 12 CHECK (cooldown_hours BETWEEN 0 AND 168),
    score             INT,
    total             INT,
    percent           NUMERIC(5, 2),
    duration_s        INT,
    answers           JSONB,                           -- submitted answers {question id: "A".."D"}
    results           JSONB,                           -- per question: correct or not
    wildcards_spent   INT NOT NULL DEFAULT 0 CHECK (wildcards_spent >= 0),
    access_request_id UUID REFERENCES quiz_access_requests(request_id),
    FOREIGN KEY (quiz_id, quiz_version) REFERENCES quiz_versions(quiz_id, version),
    UNIQUE (user_id, start_key),
    CHECK (status <> 'completed' OR (score IS NOT NULL AND total > 0 AND percent IS NOT NULL AND ended_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quiz_attempt_active  ON quiz_attempts(user_id) WHERE status = 'in_progress';
CREATE UNIQUE INDEX IF NOT EXISTS uq_quiz_attempt_request ON quiz_attempts(access_request_id) WHERE access_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user    ON quiz_attempts(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_results ON quiz_attempts(status, ended_at DESC);

-- Every wildcard movement (quiz force, AR skip/jump/earn, daily gift, admin gift)
CREATE TABLE IF NOT EXISTS wildcard_ledger (
    entry_id        BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    delta           INT  NOT NULL,
    reason          TEXT NOT NULL,
    ref             TEXT,
    idempotency_key TEXT UNIQUE,
    gift_after      INT,
    default_after   INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wildcard_ledger_user ON wildcard_ledger(user_id, created_at DESC);

-- Sensitive admin actions (quiz approvals/rejections, ...)
CREATE TABLE IF NOT EXISTS admin_audit_log (
    entry_id       BIGSERIAL PRIMARY KEY,
    admin_user_id  TEXT,
    admin_username TEXT,
    action         TEXT NOT NULL,
    target_user_id TEXT,
    target_id      TEXT,
    details        JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at DESC);

-- Ranking-ready summary (version 1), derived only from COMPLETED attempts.
--   ranking_score_v1 = 0.5 * avg_percent + 0.3 * best_percent + 0.2 * recent_avg_percent (last 3)
--   tie-break (if a ranking is ever shown): ranking_score_v1 DESC, avg_percent DESC, best_percent DESC,
--   last_completed_at ASC, user_id ASC. Attempt counts alone never raise the score.
CREATE OR REPLACE VIEW quiz_user_performance_v1 AS
WITH c AS (
    SELECT user_id, username, score, total, percent, ended_at,
           row_number() OVER (PARTITION BY user_id ORDER BY ended_at DESC, attempt_id) AS rn
    FROM quiz_attempts WHERE status = 'completed'
)
SELECT user_id,
       max(username)                                                   AS username,
       count(*)                                                        AS completed_attempts,
       max(percent)                                                    AS best_percent,
       round(avg(percent), 2)                                          AS avg_percent,
       round(avg(percent) FILTER (WHERE rn <= 3), 2)                   AS recent_avg_percent,
       round(coalesce(stddev_pop(percent), 0), 2)                      AS percent_stddev,
       max(ended_at)                                                   AS last_completed_at,
       (array_agg(score   ORDER BY ended_at DESC))[1]                  AS latest_score,
       (array_agg(total   ORDER BY ended_at DESC))[1]                  AS latest_total,
       (array_agg(percent ORDER BY ended_at DESC))[1]                  AS latest_percent,
       round(0.5 * avg(percent) + 0.3 * max(percent)
             + 0.2 * avg(percent) FILTER (WHERE rn <= 3), 2)           AS ranking_score_v1
FROM c
GROUP BY user_id;
