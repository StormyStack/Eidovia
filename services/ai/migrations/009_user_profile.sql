-- ==========================================================
-- Profile page in the app: age and gender (both optional).
-- The gateway also adds these columns at runtime (ADD COLUMN IF NOT EXISTS).
-- ==========================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS age INT CHECK (age IS NULL OR age BETWEEN 5 AND 120);
ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT;
