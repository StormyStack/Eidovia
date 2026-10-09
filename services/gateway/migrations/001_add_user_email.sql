-- 001_add_user_email.sql
-- Adds a nullable, case-insensitively unique email column to users.
-- Additive and idempotent: safe to run more than once; existing rows are untouched.
-- NEEDS SE AGREEMENT (see docs/api-auth-home.md). Does not modify 01_schema.sql.
--
-- Rollback (if ever needed):
--   DROP INDEX IF EXISTS uq_users_email_lower;
--   ALTER TABLE users DROP COLUMN IF EXISTS email;

ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;

-- Unique, case-insensitive. Multiple NULLs are allowed, so existing users without email stay valid.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (lower(email));
