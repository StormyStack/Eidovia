"""
Audit trail for administrative actions.

Two records per sensitive action:
  * admin_audit_log (migration 010): who did what to whom, with the changes. Only ever INSERTed; the admin app
    has no route that updates or deletes it.
  * an event in the learner's activity log (audit_logs, via the logger) with "by" = the administrator, so the
    action shows up in that user's Activity Logs next to everything else they did.
Timestamps are server time (database now() / the admin service's UTC clock), never the browser's.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from redis_client import get_redis

logger = logging.getLogger(__name__)

# same definition as services/ai/migrations/010_quiz.sql (older databases get it here)
_DDL = [
    """CREATE TABLE IF NOT EXISTS admin_audit_log (
           entry_id       BIGSERIAL PRIMARY KEY,
           admin_user_id  TEXT,
           admin_username TEXT,
           action         TEXT NOT NULL,
           target_user_id TEXT,
           target_id      TEXT,
           details        JSONB NOT NULL DEFAULT '{}',
           created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
       )""",
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit_log(target_user_id, created_at DESC)",
]
_ready = False


async def _ensure(session) -> None:
    global _ready
    if not _ready:
        for sql in _DDL:
            await session.execute(text(sql))
        _ready = True


async def record(session, admin, action: str, target_user_id: Optional[str], details: dict[str, Any],
                 target_id: Optional[str] = None) -> None:
    """Write one admin_audit_log row in the caller's transaction (kept or rolled back together with the change)."""
    await _ensure(session)
    await session.execute(text("""
        INSERT INTO admin_audit_log (admin_user_id, admin_username, action, target_user_id, target_id, details)
        VALUES (CAST(:aid AS TEXT), CAST(:an AS TEXT), CAST(:act AS TEXT), CAST(:tu AS TEXT), CAST(:tid AS TEXT),
                CAST(:d AS JSONB))
    """), {"aid": str(admin.user_id) if admin else None, "an": admin.username if admin else None, "act": action,
           "tu": target_user_id, "tid": target_id or target_user_id, "d": json.dumps(details, default=str)})


async def user_event(action: str, user_id: str, username: str, details: dict[str, Any]) -> None:
    """Add an event to the user's activity log (through the logger, like every other event). Best effort."""
    try:
        r = await get_redis()
        await r.rpush("raw_audit_logs", json.dumps({
            "action": action, "user_id": user_id, "username": username, "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, default=str))
    except Exception as e:  # the change itself is saved; only this log line is missing
        logger.warning(f"Could not queue audit event {action}: {e}")
