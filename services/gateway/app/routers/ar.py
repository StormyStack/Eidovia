"""
AR game routes for the mobile app.

GET /api/ar/progress   the learner's dashboard on the DNA page (built from their audit_logs)

The game's wildcards use the app-wide wallet in routers/wildcards.py (feature "ar").
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.db import db
from app.deps import CurrentUser, get_current_user
from app.routers.wildcards import AR_LEVELS as LEVEL_NAMES, log_daily_gift, wallet_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ar", tags=["ar"])


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.get("/progress")
async def get_progress(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """The learner's DNA journey: levels, time played, wildcards (total only) and chat questions."""
    uid = current_user.user_id
    level = "(CASE WHEN details->>'level' ~ '^[0-9]+$' THEN (details->>'level')::int END)"
    duration = "(CASE WHEN details->>'duration_s' ~ '^[0-9]+(\\.[0-9]+)?$' THEN (details->>'duration_s')::numeric END)"
    async with db.get_session() as session:
        wallet, daily = await wallet_for(session, uid)
        totals = (await session.execute(text(f"""
            SELECT
                COUNT(DISTINCT details->>'session_id') FILTER (WHERE action = 'ar_session_start')  AS sessions,
                COALESCE(SUM({duration}) FILTER (WHERE action = 'ar_session_end'), 0)              AS play_seconds,
                COUNT(*) FILTER (WHERE action = 'ar_part_discovered')                              AS parts,
                COUNT(*) FILTER (WHERE action = 'ar_journey_completed')                            AS finished,
                COUNT(*) FILTER (WHERE action = 'wildcard_used' AND details->>'feature' = 'ar' AND details->>'paid' = 'true')  AS wild_used,
                COUNT(*) FILTER (WHERE action = 'wildcard_used' AND details->>'feature' = 'ar' AND details->>'paid' = 'true'
                                   AND details->>'mode' = 'jump')                                  AS jumps,
                COUNT(*) FILTER (WHERE action = 'ar_previous_used')                                AS back_used,
                COUNT(*) FILTER (WHERE action = 'message_sent')                                    AS chats,
                MAX(created_at) FILTER (WHERE action IN ('ar_session_start','ar_session_end'))     AS last_played
            FROM audit_logs WHERE user_id = :u
        """), {"u": uid})).first()

        stages = (await session.execute(text(f"""
            SELECT {level} AS level,
                   BOOL_OR(details->>'skipped' IS DISTINCT FROM 'true') AS passed
            FROM audit_logs
            WHERE user_id = :u AND action = 'ar_stage_completed'
            GROUP BY 1
        """), {"u": uid})).all()

        # where the learner is now: the latest event that tells a level
        last = (await session.execute(text("""
            SELECT action, details FROM audit_logs
            WHERE user_id = :u AND action IN ('ar_session_end','ar_part_discovered','ar_stage_completed',
                                              'wildcard_used','ar_previous_used')
              AND (action <> 'wildcard_used' OR details->>'feature' = 'ar')
            ORDER BY created_at DESC LIMIT 1
        """), {"u": uid})).first()
    await log_daily_gift(current_user, wallet, daily)

    count = len(LEVEL_NAMES)
    passed = {r.level for r in stages if r.level and r.passed}
    skipped = {r.level for r in stages if r.level and not r.passed}

    current = None
    if last is not None:
        d = last.details or {}
        if last.action == "ar_previous_used" or (last.action == "wildcard_used" and d.get("paid") is not False):
            current = _int(d.get("to_level"))
        elif last.action == "wildcard_used":
            current = _int(d.get("from_level"))
        elif last.action == "ar_stage_completed":
            lv = _int(d.get("level"))
            current = min(lv + 1, count) if lv else None
        else:
            current = _int(d.get("level"))
    if current is not None and not 1 <= current <= count:
        current = None

    levels = [
        {"level": i, "name": name, "status": "passed" if i in passed else "skipped" if i in skipped else "not_yet",
         "current": i == current}
        for i, name in enumerate(LEVEL_NAMES, start=1)
    ]
    return {
        "levels": levels,
        "level_count": count,
        "levels_passed": len(passed),
        "levels_skipped": len(skipped),
        "current_level": current,
        "current_level_name": LEVEL_NAMES[current - 1] if current else None,
        "finished": (totals.finished or 0) > 0,
        "times_finished": totals.finished or 0,
        "sessions": totals.sessions or 0,
        "play_seconds": round(float(totals.play_seconds or 0)),
        "parts_discovered": totals.parts or 0,
        "wildcards": wallet["total"],
        "wildcards_used": totals.wild_used or 0,
        "power_jumps": totals.jumps or 0,
        "back_used": totals.back_used or 0,
        "chat_questions": totals.chats or 0,
        "last_played": totals.last_played.isoformat() if totals.last_played else None,
    }
