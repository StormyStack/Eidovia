-- ==========================================================
-- Support tickets can be wildcard requests from the app (DNA page → "Ask for wildcards").
--   kind              'general' | 'wildcard'
--   requested_amount  wildcards the learner asked for
--   granted_amount    wildcards an admin gave when resolving it
-- The gateway and admin also add these columns at runtime (ADD COLUMN IF NOT EXISTS).
-- ==========================================================

ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'general';
ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS requested_amount INT;
ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS granted_amount INT;
CREATE INDEX IF NOT EXISTS idx_support_tickets_user_kind ON support_tickets(user_id, kind);
