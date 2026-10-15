"""
Wildcards: one wallet per learner (not per phone), for the whole app. Today the AR game spends and earns them;
other features can use the same wallet later by adding their own entry to COSTS / EARN_RULES.

  total = gift + default            the learner only ever sees the total
  gift     +2 every 24 h, at most 6 (topped up whenever the wallet is read)
  default  starts at 3; admin gifts and earned cards go here
  spending takes gift cards first, then default cards

GET  /api/wildcards            total, and whether the learner may ask for more (app home + DNA page)
POST /api/wildcards/sync       total + cards the game should announce (daily gift / admin gift), clears "unseen"
POST /api/wildcards/spend      pay for an action: {feature, action, ...}   e.g. ar/skip = 1, ar/jump = 2
POST /api/wildcards/earn       earn a card: {feature, reason, ...}          e.g. ar/level_passed
POST /api/wildcards/request    ask an admin for wildcards with a reason (a support ticket; once every 3 days)
GET  /api/wildcards/requests   the learner's recent requests and the admin's answers

Every change is also a row in wildcard_ledger (delta, reason, wallet after; idempotency key where it matters).
Audit events (admin panel): wildcard_used, wildcard_earned, wildcard_daily_gift, wildcard_requested
(the admin panel writes wildcards_granted). Each has the wallet after the change: gift, default, total.
"""

import logging
from datetime import timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import db
from app.deps import CurrentUser, get_current_user
from app.errors import ApiError
from app.logger_client import push_log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wildcards", tags=["wildcards"])

START_CARDS = 3          # default cards of a new learner
DAILY_GIFT = 2           # gift cards every 24 hours
GIFT_MAX = 6             # gift cards never go above this
DAY = timedelta(hours=24)
REQUEST_EVERY = timedelta(days=3)    # a learner can ask an admin for wildcards once every 3 days

# what each feature may spend wildcards on, and the price
COSTS: dict[str, dict[str, int]] = {
    "ar": {"skip": 1, "jump": 2},     # AR game: skip a level / jump to any level
}
# what earns a card: (feature, reason) -> only while the total is below this
EARN_RULES: dict[tuple[str, str], int] = {
    ("ar", "level_passed"): 5,        # AR game: a level finished without a wildcard
}

AR_LEVELS = ["The building blocks", "A nucleotide", "A single strand", "Two strands", "The double helix"]

SETUP = [
    # wallets were first called ar_wallets; keep the cards when upgrading
    """DO $$ BEGIN
         IF to_regclass('public.ar_wallets') IS NOT NULL AND to_regclass('public.wildcard_wallets') IS NULL THEN
           ALTER TABLE ar_wallets RENAME TO wildcard_wallets;
         END IF;
       END $$""",
    """CREATE TABLE IF NOT EXISTS wildcard_wallets (
         user_id TEXT PRIMARY KEY,
         default_cards INT NOT NULL DEFAULT 3 CHECK (default_cards >= 0),
         gift_cards INT NOT NULL DEFAULT 0 CHECK (gift_cards >= 0),
         last_gift_at TIMESTAMPTZ,
         unseen INT NOT NULL DEFAULT 0,
         created_at TIMESTAMPTZ DEFAULT now(),
         updated_at TIMESTAMPTZ DEFAULT now()
       )""",
    "ALTER TABLE IF EXISTS support_tickets ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'general'",
    "ALTER TABLE IF EXISTS support_tickets ADD COLUMN IF NOT EXISTS requested_amount INT",
    "ALTER TABLE IF EXISTS support_tickets ADD COLUMN IF NOT EXISTS granted_amount INT",
    # auditable ledger of every wildcard movement (migration 010)
    """CREATE TABLE IF NOT EXISTS wildcard_ledger (
         entry_id BIGSERIAL PRIMARY KEY,
         user_id TEXT NOT NULL,
         delta INT NOT NULL,
         reason TEXT NOT NULL,
         ref TEXT,
         idempotency_key TEXT UNIQUE,
         gift_after INT,
         default_after INT,
         created_at TIMESTAMPTZ NOT NULL DEFAULT now()
       )""",
    "CREATE INDEX IF NOT EXISTS idx_wildcard_ledger_user ON wildcard_ledger(user_id, created_at DESC)",
]
_ready = False


async def _setup(session) -> None:
    """Migrations 007/008 do this on a fresh database; older databases get it here once."""
    global _ready
    if not _ready:
        for sql in SETUP:
            await session.execute(text(sql))
        _ready = True


async def wallet_for(session, user_id: str) -> tuple[dict, int]:
    """
    Lock and return the learner's wallet (created on first use), after topping up the daily gift.
    Returns (wallet {gift, default, total, unseen}, cards added by the daily gift now).
    """
    await _setup(session)
    await session.execute(text(
        "INSERT INTO wildcard_wallets (user_id, default_cards) VALUES (:u, :start) ON CONFLICT (user_id) DO NOTHING"
    ), {"u": user_id, "start": START_CARDS})
    w = (await session.execute(text(
        "SELECT gift_cards, default_cards, last_gift_at, unseen, now() AS now FROM wildcard_wallets WHERE user_id = :u FOR UPDATE"
    ), {"u": user_id})).first()
    wallet = {"gift": w.gift_cards, "default": w.default_cards, "unseen": w.unseen}

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
            "UPDATE wildcard_wallets SET gift_cards = :g, last_gift_at = :t, unseen = unseen + :a, updated_at = now() WHERE user_id = :u"
        ), {"g": new_gift, "t": last, "a": added, "u": user_id})
        wallet.update(gift=new_gift, unseen=w.unseen + added)
        if added:
            await ledger(session, user_id, added, "daily_gift", wallet)
    wallet["total"] = wallet["gift"] + wallet["default"]
    return wallet, added


async def ledger(session, user_id: str, delta: int, reason: str, wallet: dict,
                 ref: Optional[str] = None, key: Optional[str] = None) -> None:
    """One row in wildcard_ledger (same transaction as the wallet change). key = idempotency key (unique)."""
    await session.execute(text("""
        INSERT INTO wildcard_ledger (user_id, delta, reason, ref, idempotency_key, gift_after, default_after)
        VALUES (CAST(:u AS TEXT), CAST(:d AS INT), CAST(:r AS TEXT), CAST(:ref AS TEXT), CAST(:k AS TEXT),
                CAST(:g AS INT), CAST(:df AS INT))
    """), {"u": user_id, "d": delta, "r": reason, "ref": ref, "k": key, "g": wallet["gift"], "df": wallet["default"]})


async def deduct(session, user_id: str, wallet: dict, cost: int) -> tuple[int, int]:
    """
    Take `cost` cards from a wallet locked by wallet_for() (gift cards first). The caller checked the total.
    Updates `wallet` in place and returns (from_gift, from_default).
    """
    from_gift = min(wallet["gift"], cost)
    from_default = cost - from_gift
    await session.execute(text(
        "UPDATE wildcard_wallets SET gift_cards = gift_cards - CAST(:g AS INT), "
        "default_cards = default_cards - CAST(:d AS INT), updated_at = now() WHERE user_id = :u"
    ), {"g": from_gift, "d": from_default, "u": user_id})
    wallet["gift"] -= from_gift
    wallet["default"] -= from_default
    wallet["total"] -= cost
    return from_gift, from_default


async def log_daily_gift(user: CurrentUser, wallet: dict, added: int) -> None:
    if added > 0:
        await push_log_event("wildcard_daily_gift", user.user_id, user.username, user.is_admin, {
            "added": added, "gift": wallet["gift"], "default": wallet["default"], "total": wallet["total"],
        })


def _ar_level(n: Optional[int]) -> Optional[str]:
    return AR_LEVELS[n - 1] if n and 1 <= n <= len(AR_LEVELS) else None


def _request_out(r) -> dict:
    return {
        "ticket_id": str(r.ticket_id),
        "amount": r.requested_amount,
        "reason": r.message,
        "status": r.status,                       # open | in_progress | resolved
        "granted": r.granted_amount,              # cards given when resolved (null / 0 = not given)
        "admin_reply": r.admin_notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


async def _requests(session, user_id: str) -> dict:
    rows = (await session.execute(text("""
        SELECT ticket_id, requested_amount, message, status, granted_amount, admin_notes, created_at, updated_at, now() AS now
        FROM support_tickets WHERE user_id = :u AND kind = 'wildcard'
        ORDER BY created_at DESC LIMIT 5
    """), {"u": user_id})).all()
    can = not rows or (rows[0].status == "resolved" and rows[0].created_at + REQUEST_EVERY <= rows[0].now)
    next_at = None if can or not rows else (rows[0].created_at + REQUEST_EVERY).isoformat()
    return {"requests": [_request_out(r) for r in rows], "can_request": can, "next_request_at": next_at}


# ============================================================
# WALLET
# ============================================================

@router.get("")
async def get_wildcards(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """The learner's total (never the gift/default split) and their wildcard requests."""
    async with db.get_session() as session:
        wallet, daily = await wallet_for(session, current_user.user_id)
        requests = await _requests(session, current_user.user_id)
    await log_daily_gift(current_user, wallet, daily)
    return {"total": wallet["total"], **requests}


@router.post("/sync")
async def sync_wildcards(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Total cards, and how many arrived since the last sync (daily gift or an admin's gift) for the game to announce."""
    async with db.get_session() as session:
        wallet, daily = await wallet_for(session, current_user.user_id)
        unseen = wallet["unseen"]
        if unseen:
            await session.execute(text("UPDATE wildcard_wallets SET unseen = 0 WHERE user_id = :u"), {"u": current_user.user_id})
    await log_daily_gift(current_user, wallet, daily)
    return {"total": wallet["total"], "added": unseen}


class SpendRequest(BaseModel):
    feature: str = Field("ar", max_length=40)
    action: str = Field(..., max_length=40)
    session_id: Optional[str] = Field(None, max_length=100)
    # AR game
    from_level: Optional[int] = Field(None, ge=1, le=len(AR_LEVELS))
    to_level: Optional[int] = Field(None, ge=1, le=len(AR_LEVELS))


@router.post("/spend")
async def spend_wildcards(body: SpendRequest, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Pay for an action (gift cards first). The price comes from COSTS, never from the app. ok = false: not enough."""
    cost = COSTS.get(body.feature, {}).get(body.action)
    if cost is None:
        raise ApiError(400, "VALIDATION_ERROR", f"Wildcards cannot be used for {body.feature}/{body.action}.")
    async with db.get_session() as session:
        wallet, daily = await wallet_for(session, current_user.user_id)
        ok = wallet["total"] >= cost
        from_gift = from_default = 0
        if ok:
            from_gift, from_default = await deduct(session, current_user.user_id, wallet, cost)
            await ledger(session, current_user.user_id, -cost, f"{body.feature}_{body.action}", wallet, ref=body.session_id)
    await log_daily_gift(current_user, wallet, daily)
    details: dict[str, Any] = {
        "feature": body.feature, "action": body.action, "mode": body.action, "session_id": body.session_id,
        "cost": cost, "paid": ok, "from_gift": from_gift, "from_default": from_default,
        "gift": wallet["gift"], "default": wallet["default"], "wildcards_left": wallet["total"],
    }
    if body.feature == "ar":
        details.update(from_level=body.from_level, from_name=_ar_level(body.from_level),
                       to_level=body.to_level, to_name=_ar_level(body.to_level))
    await push_log_event("wildcard_used", current_user.user_id, current_user.username, current_user.is_admin, details)
    return {"ok": ok, "total": wallet["total"]}


class EarnRequest(BaseModel):
    feature: str = Field("ar", max_length=40)
    reason: str = Field("level_passed", max_length=40)
    session_id: Optional[str] = Field(None, max_length=100)
    level: Optional[int] = Field(None, ge=1, le=len(AR_LEVELS))   # AR game


@router.post("/earn")
async def earn_wildcard(body: EarnRequest, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """+1 default card when EARN_RULES allows it (e.g. an AR level passed while the total is below 5)."""
    below = EARN_RULES.get((body.feature, body.reason))
    if below is None:
        raise ApiError(400, "VALIDATION_ERROR", f"Nothing to earn for {body.feature}/{body.reason}.")
    async with db.get_session() as session:
        wallet, daily = await wallet_for(session, current_user.user_id)
        earned = wallet["total"] < below
        if earned:
            await session.execute(text(
                "UPDATE wildcard_wallets SET default_cards = default_cards + 1, updated_at = now() WHERE user_id = :u"
            ), {"u": current_user.user_id})
            wallet["default"] += 1
            wallet["total"] += 1
            await ledger(session, current_user.user_id, 1, f"{body.feature}_{body.reason}", wallet, ref=body.session_id)
    await log_daily_gift(current_user, wallet, daily)
    if earned:
        details: dict[str, Any] = {"feature": body.feature, "reason": body.reason, "session_id": body.session_id,
                                   "gift": wallet["gift"], "default": wallet["default"], "total": wallet["total"]}
        if body.feature == "ar":
            details.update(level=body.level, level_name=_ar_level(body.level))
        await push_log_event("wildcard_earned", current_user.user_id, current_user.username, current_user.is_admin, details)
    return {"earned": earned, "total": wallet["total"]}


# ============================================================
# REQUESTS (support tickets of kind 'wildcard', answered in the admin panel)
# ============================================================

class WildcardRequest(BaseModel):
    amount: int = Field(..., ge=1, le=10)
    reason: str = Field(..., min_length=5, max_length=500)


@router.post("/request", status_code=201)
async def request_wildcards(body: WildcardRequest, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Once every 3 days and one open request at a time. It shows up in the admin panel under User Support."""
    reason = body.reason.strip()
    if len(reason) < 5:
        raise ApiError(400, "VALIDATION_ERROR", "Please tell us why you need wildcards.", {"reason": "At least 5 characters."})
    async with db.get_session() as session:
        await _setup(session)
        last = (await session.execute(text("""
            SELECT created_at, status, now() AS now FROM support_tickets
            WHERE user_id = :u AND kind = 'wildcard' ORDER BY created_at DESC LIMIT 1
        """), {"u": current_user.user_id})).first()
        if last and last.now - last.created_at < REQUEST_EVERY:
            wait = REQUEST_EVERY - (last.now - last.created_at)
            hours = max(1, int(wait.total_seconds() // 3600 + 1))
            days, rest = divmod(hours, 24)
            when = (f"{days} day{'s' if days != 1 else ''}" + (f" {rest} h" if rest else "")) if days else f"{hours} h"
            raise ApiError(429, "REQUEST_TOO_SOON", f"You can ask for wildcards once every 3 days. Try again in {when}.")
        if last and last.status != "resolved":
            raise ApiError(409, "REQUEST_PENDING", "You already asked for wildcards. Please wait for the answer.")
        row = (await session.execute(text("""
            INSERT INTO support_tickets (user_id, username, subject, message, priority, status, kind, requested_amount)
            VALUES (:u, :name, :subject, :message, 'medium', 'open', 'wildcard', :amount)
            RETURNING ticket_id, requested_amount, message, status, granted_amount, admin_notes, created_at, updated_at
        """), {"u": current_user.user_id, "name": current_user.username, "amount": body.amount, "message": reason,
               "subject": f"Wildcard request: {body.amount} card{'s' if body.amount != 1 else ''}"})).first()
    await push_log_event("wildcard_requested", current_user.user_id, current_user.username, current_user.is_admin, {
        "amount": body.amount, "reason": reason, "ticket_id": str(row.ticket_id),
    })
    return _request_out(row)


@router.get("/requests")
async def my_wildcard_requests(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """The learner's last 5 wildcard requests (newest first) and when they may ask again."""
    async with db.get_session() as session:
        await _setup(session)
        return await _requests(session, current_user.user_id)
