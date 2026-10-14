"""
AR game routes for the mobile app. The wildcard wallet lives here (one per learner, not per phone).

  total = gift + default            the learner only ever sees the total
  gift     +2 every 24 h, at most 6 (topped up whenever the wallet is read)
  default  starts at 3; admin gifts and cards earned by finishing a level go here
  spending takes gift cards first, then default cards

POST /api/ar/wallet/sync   apply the daily gift; returns {total, added} (added = new cards the game should announce)
POST /api/ar/wallet/spend  the game used a wildcard: skip = 1 card, jump = 2 cards
POST /api/ar/wallet/earn   the game finished a level on its own and earned a card
GET  /api/ar/progress      the learner's dashboard on the DNA page (built from their audit_logs)

Every wallet change is written to the audit log with the full breakdown for the admin panel.
"""

import logging
from datetime import timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import db
from app.deps import CurrentUser, get_current_user
from app.logger_client import push_log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ar", tags=["ar"])

LEVEL_NAMES = ["The building blocks", "A nucleotide", "A single strand", "Two strands", "The double helix"]

START_CARDS = 3          # default cards of a new learner
DAILY_GIFT = 2           # gift cards every 24 hours
GIFT_MAX = 6             # gift cards never go above this
EARN_BELOW = 5           # a finished level earns a card only while the total is below this (as in the game)
COSTS = {"skip": 1, "jump": 2}
DAY = timedelta(hours=24)

WALLETS_TABLE = """
CREATE TABLE IF NOT EXISTS ar_wallets (
    user_id TEXT PRIMARY KEY,
    default_cards INT NOT NULL DEFAULT 3 CHECK (default_cards >= 0),
    gift_cards INT NOT NULL DEFAULT 0 CHECK (gift_cards >= 0),
    last_gift_at TIMESTAMPTZ,
    unseen INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
)
"""

_table_ready = False


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _level(n: Optional[int]) -> dict:
    name = LEVEL_NAMES[n - 1] if n and 1 <= n <= len(LEVEL_NAMES) else None
    return {"level": n, "name": name}


async def _wallet(session, user_id: str) -> tuple[dict, int]:
    """
    Lock and return the learner's wallet (created on first use), after topping up the daily gift.
    Returns (wallet, cards added by the daily gift now).
    """
    global _table_ready
    if not _table_ready:                      # migration 007 makes it on a fresh database
        await session.execute(text(WALLETS_TABLE))
        _table_ready = True
    await session.execute(text(
        "INSERT INTO ar_wallets (user_id, default_cards) VALUES (:u, :start) ON CONFLICT (user_id) DO NOTHING"
    ), {"u": user_id, "start": START_CARDS})
    w = (await session.execute(text(
        "SELECT gift_cards, default_cards, last_gift_at, unseen, now() AS now FROM ar_wallets WHERE user_id = :u FOR UPDATE"
    ), {"u": user_id})).first()
    wallet = {"gift": w.gift_cards, "default": w.default_cards, "unseen": w.unseen, "last_gift_at": w.last_gift_at}

    if w.last_gift_at is None:
        days, last = 1, w.now                 # first visit: today's gift right away
    else:
        days = int((w.now - w.last_gift_at) / DAY)
        last = w.last_gift_at + DAY * days
    added = 0
    if days > 0:
        new_gift = max(w.gift_cards, min(GIFT_MAX, w.gift_cards + DAILY_GIFT * days))
        added = new_gift - w.gift_cards
        await session.execute(text(
            "UPDATE ar_wallets SET gift_cards = :g, last_gift_at = :t, unseen = unseen + :a, updated_at = now() WHERE user_id = :u"
        ), {"g": new_gift, "t": last, "a": added, "u": user_id})
        wallet.update(gift=new_gift, unseen=w.unseen + added, last_gift_at=last)
    wallet["total"] = wallet["gift"] + wallet["default"]
    return wallet, added


async def _log_daily_gift(user: CurrentUser, wallet: dict, added: int) -> None:
    if added > 0:
        await push_log_event("ar_daily_gift", user.user_id, user.username, user.is_admin, {
            "added": added, "gift": wallet["gift"], "default": wallet["default"], "total": wallet["total"],
        })


# ============================================================
# WALLET
# ============================================================

@router.post("/wallet/sync")
async def sync_wallet(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Total cards, and how many arrived since the game last asked (daily gift or an admin's gift)."""
    async with db.get_session() as session:
        wallet, daily = await _wallet(session, current_user.user_id)
        unseen = wallet["unseen"]
        if unseen:
            await session.execute(text("UPDATE ar_wallets SET unseen = 0 WHERE user_id = :u"), {"u": current_user.user_id})
    await _log_daily_gift(current_user, wallet, daily)
    return {"total": wallet["total"], "added": unseen}


class SpendRequest(BaseModel):
    mode: Literal["skip", "jump"]
    from_level: int = Field(..., ge=1, le=len(LEVEL_NAMES))
    to_level: int = Field(..., ge=1, le=len(LEVEL_NAMES))
    session_id: Optional[str] = Field(None, max_length=100)


@router.post("/wallet/spend")
async def spend_wildcards(body: SpendRequest, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Pay for a wildcard (gift cards first). ok = false when the learner did not have enough."""
    cost = COSTS[body.mode]
    async with db.get_session() as session:
        wallet, daily = await _wallet(session, current_user.user_id)
        ok = wallet["total"] >= cost
        from_gift = min(wallet["gift"], cost) if ok else 0
        from_default = cost - from_gift if ok else 0
        if ok:
            await session.execute(text(
                "UPDATE ar_wallets SET gift_cards = gift_cards - :g, default_cards = default_cards - :d, updated_at = now() "
                "WHERE user_id = :u"
            ), {"g": from_gift, "d": from_default, "u": current_user.user_id})
            wallet["gift"] -= from_gift
            wallet["default"] -= from_default
            wallet["total"] -= cost
    await _log_daily_gift(current_user, wallet, daily)
    a, b = _level(body.from_level), _level(body.to_level)
    await push_log_event("ar_wildcard_used", current_user.user_id, current_user.username, current_user.is_admin, {
        "session_id": body.session_id, "mode": body.mode, "cost": cost, "paid": ok,
        "from_level": a["level"], "from_name": a["name"], "to_level": b["level"], "to_name": b["name"],
        "from_gift": from_gift, "from_default": from_default,
        "gift": wallet["gift"], "default": wallet["default"], "wildcards_left": wallet["total"],
    })
    return {"ok": ok, "total": wallet["total"]}


class EarnRequest(BaseModel):
    level: int = Field(..., ge=1, le=len(LEVEL_NAMES))
    session_id: Optional[str] = Field(None, max_length=100)


@router.post("/wallet/earn")
async def earn_wildcard(body: EarnRequest, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """+1 default card for finishing a level on one's own, only while the total is below EARN_BELOW."""
    async with db.get_session() as session:
        wallet, daily = await _wallet(session, current_user.user_id)
        earned = wallet["total"] < EARN_BELOW
        if earned:
            await session.execute(text(
                "UPDATE ar_wallets SET default_cards = default_cards + 1, updated_at = now() WHERE user_id = :u"
            ), {"u": current_user.user_id})
            wallet["default"] += 1
            wallet["total"] += 1
    await _log_daily_gift(current_user, wallet, daily)
    if earned:
        lv = _level(body.level)
        await push_log_event("ar_wildcard_earned", current_user.user_id, current_user.username, current_user.is_admin, {
            "session_id": body.session_id, "level": lv["level"], "level_name": lv["name"],
            "gift": wallet["gift"], "default": wallet["default"], "total": wallet["total"],
        })
    return {"earned": earned, "total": wallet["total"]}


# ============================================================
# DASHBOARD
# ============================================================

@router.get("/progress")
async def get_progress(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """The learner's DNA journey: levels, time played, wildcards (total only) and chat questions."""
    uid = current_user.user_id
    level = "(CASE WHEN details->>'level' ~ '^[0-9]+$' THEN (details->>'level')::int END)"
    duration = "(CASE WHEN details->>'duration_s' ~ '^[0-9]+(\\.[0-9]+)?$' THEN (details->>'duration_s')::numeric END)"
    async with db.get_session() as session:
        wallet, daily = await _wallet(session, uid)
        totals = (await session.execute(text(f"""
            SELECT
                COUNT(DISTINCT details->>'session_id') FILTER (WHERE action = 'ar_session_start')  AS sessions,
                COALESCE(SUM({duration}) FILTER (WHERE action = 'ar_session_end'), 0)              AS play_seconds,
                COUNT(*) FILTER (WHERE action = 'ar_part_discovered')                              AS parts,
                COUNT(*) FILTER (WHERE action = 'ar_journey_completed')                            AS finished,
                COUNT(*) FILTER (WHERE action = 'ar_wildcard_used' AND details->>'paid' = 'true')  AS wild_used,
                COUNT(*) FILTER (WHERE action = 'ar_wildcard_used' AND details->>'paid' = 'true'
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
                                              'ar_wildcard_used','ar_previous_used')
            ORDER BY created_at DESC LIMIT 1
        """), {"u": uid})).first()
    await _log_daily_gift(current_user, wallet, daily)

    count = len(LEVEL_NAMES)
    passed = {r.level for r in stages if r.level and r.passed}
    skipped = {r.level for r in stages if r.level and not r.passed}

    current = None
    if last is not None:
        d = last.details or {}
        if last.action == "ar_previous_used" or (last.action == "ar_wildcard_used" and d.get("paid") is not False):
            current = _int(d.get("to_level"))
        elif last.action == "ar_wildcard_used":
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
