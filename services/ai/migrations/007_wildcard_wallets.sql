-- ==========================================================
-- Wildcards for the whole app, one wallet per learner (server is the source of truth).
--   total = gift_cards + default_cards   (the learner only sees the total)
--   gift_cards     +2 every 24 h, never more than 6 (applied by the gateway when the wallet is read)
--   default_cards  starts at 3; admin gifts and cards earned by finishing a level are added here
--   spending takes gift cards first, then default cards
--   unseen         cards added (daily gift / admin) that the game has not announced yet
-- The gateway and admin also create this table at runtime (CREATE TABLE IF NOT EXISTS).
-- ==========================================================

CREATE TABLE IF NOT EXISTS wildcard_wallets (
    user_id TEXT PRIMARY KEY,
    default_cards INT NOT NULL DEFAULT 3 CHECK (default_cards >= 0),
    gift_cards INT NOT NULL DEFAULT 0 CHECK (gift_cards >= 0),
    last_gift_at TIMESTAMPTZ,
    unseen INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
