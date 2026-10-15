"""
AR game analytics for the admin panel.

Source: audit_logs rows with an ar_* action, written by the logger service from the mobile app's AR events
(apps/mobile/src/services/ArTelemetry.ts → POST /api/events → Redis → logger → audit_logs).

details of each action:
  ar_session_start      session_id, module_id
  ar_part_discovered    session_id, level, level_name, part
  ar_stage_completed    session_id, level, level_name, skipped, duration_s, parts_found, parts_required
  ar_journey_completed  session_id, duration_s
  ar_session_end        session_id, duration_s, level, level_name, parts_found, parts_required, wildcards_left,
                        ar (false = 3D mode: the phone has no ARCore)
  ar_previous_used      session_id, from_level, from_name, to_level, to_name   (Back button, once per 30 s)

Wildcards are app-wide (gateway routers/wildcards.py, table wildcard_wallets, one per learner; total = gift + default,
the learner only sees the total). The AR game is feature "ar":
  wildcard_used         written by the gateway: feature, action/mode (ar: skip = 1 card, jump = 2), cost, paid, from/to level,
                        from_gift, from_default (gift cards are spent first), gift, default, wildcards_left
  wildcard_earned       gateway: feature, reason, level, level_name, gift, default, total   (+1 default card)
  wildcard_daily_gift   gateway: added, gift, default, total   (+2 gift cards every 24 h, gift max 6)
  wildcard_requested    gateway: amount, reason, ticket_id   (the learner asked from the app; see User Support)
  wildcards_granted     written here: amount, by, gift, default, total   (an admin's cards go to default)
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from fastapi import HTTPException
from sqlalchemy import text
from db import db
from redis_client import get_redis
from services import admin_audit

LEVEL_NAMES = ["The building blocks", "A nucleotide", "A single strand", "Two strands", "The double helix"]
AR_ACTIONS = ("('ar_session_start','ar_session_end','ar_part_discovered','ar_stage_completed','ar_journey_completed',"
              "'ar_previous_used','wildcard_used','wildcard_earned','wildcard_daily_gift','wildcards_granted',"
              "'wildcard_requested')")
MAX_GIFT = 10            # most wildcards an admin can give at once
START_CARDS = 3          # same as the gateway (services/gateway/app/routers/wildcards.py)

WALLETS_SETUP = [
    # wallets were first called ar_wallets; keep the cards when upgrading
    """DO $$ BEGIN
         IF to_regclass('public.ar_wallets') IS NOT NULL AND to_regclass('public.wildcard_wallets') IS NULL THEN
           ALTER TABLE ar_wallets RENAME TO wildcard_wallets;
         END IF;
       END $$""",
    """
CREATE TABLE IF NOT EXISTS wildcard_wallets (
    user_id TEXT PRIMARY KEY,
    default_cards INT NOT NULL DEFAULT 3 CHECK (default_cards >= 0),
    gift_cards INT NOT NULL DEFAULT 0 CHECK (gift_cards >= 0),
    last_gift_at TIMESTAMPTZ,
    unseen INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
)
""",
    # every wildcard movement (same definition as migration 010 / the gateway)
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
_table_ready = False


async def _ensure_table(session) -> None:
    """Migration 007 makes the table on a fresh database; older databases get it here."""
    global _table_ready
    if not _table_ready:
        for sql in WALLETS_SETUP:
            await session.execute(text(sql))
        _table_ready = True


# numbers come from the app as JSON; only cast values that really are numbers
LEVEL = "(CASE WHEN details->>'level' ~ '^[0-9]+$' THEN (details->>'level')::int END)"
DURATION = "(CASE WHEN details->>'duration_s' ~ '^[0-9]+(\\.[0-9]+)?$' THEN (details->>'duration_s')::numeric END)"
SKIPPED = "(details->>'skipped' = 'true')"
COST = "(CASE WHEN details->>'cost' ~ '^[0-9]+$' AND details->>'paid' = 'true' THEN (details->>'cost')::int END)"
AMOUNT = "(CASE WHEN details->>'{0}' ~ '^[0-9]+$' THEN (details->>'{0}')::int END)"
PAID = "(action = 'wildcard_used' AND details->>'paid' = 'true')"
TO_LEVEL = "(CASE WHEN details->>'to_level' ~ '^[0-9]+$' THEN (details->>'to_level')::int END)"
# the level the learner is on after this event (a finished level moves them to the next one)
NOW_LEVEL = (f"(CASE WHEN action = 'ar_previous_used' OR {PAID} THEN {TO_LEVEL} "
             f"WHEN action = 'ar_stage_completed' THEN LEAST({LEVEL} + 1, {len(LEVEL_NAMES)}) ELSE {LEVEL} END)")


def _num(value: Any) -> Optional[float]:
    return None if value is None else round(float(value), 1)


def _level_name(level: Optional[int]) -> Optional[str]:
    if level is None:
        return None
    return LEVEL_NAMES[level - 1] if 1 <= level <= len(LEVEL_NAMES) else f"Level {level}"


class ArService:
    @staticmethod
    async def get_summary() -> dict[str, Any]:
        async with db.get_session() as session:
            row = (await session.execute(text(f"""
                SELECT
                    COUNT(DISTINCT user_id) FILTER (WHERE action = 'ar_session_start')        AS players,
                    COUNT(DISTINCT details->>'session_id')                                     AS sessions,
                    COALESCE(SUM({DURATION}) FILTER (WHERE action = 'ar_session_end'), 0)      AS play_seconds,
                    COUNT(*) FILTER (WHERE action = 'ar_stage_completed' AND NOT {SKIPPED})    AS levels_passed,
                    COUNT(*) FILTER (WHERE action = 'ar_stage_completed' AND {SKIPPED})        AS levels_skipped,
                    COUNT(DISTINCT user_id) FILTER (WHERE action = 'ar_journey_completed')     AS finished_players,
                    COUNT(*) FILTER (WHERE action = 'ar_part_discovered')                      AS parts_discovered,
                    COUNT(*) FILTER (WHERE action = 'ar_session_end' AND details->>'ar' = 'false') AS sessions_3d,
                    COUNT(*) FILTER (WHERE {PAID})                                             AS wildcards_used,
                    COUNT(*) FILTER (WHERE {PAID} AND details->>'mode' = 'jump')               AS power_jumps,
                    COALESCE(SUM({COST}), 0)                                                   AS cards_spent,
                    COUNT(*) FILTER (WHERE action = 'ar_previous_used')                        AS back_used,
                    COALESCE(SUM({AMOUNT.format('amount')}) FILTER (WHERE action = 'wildcards_granted'), 0) AS admin_given,
                    COALESCE(SUM({AMOUNT.format('added')}) FILTER (WHERE action = 'wildcard_daily_gift'), 0)         AS daily_given,
                    COUNT(*) FILTER (WHERE action = 'wildcard_earned')                      AS earned,
                    COUNT(DISTINCT user_id) FILTER (WHERE action = 'ar_session_start' AND created_at > now() - interval '24 hours') AS players_24h,
                    MAX(created_at)                                                            AS last_activity
                FROM audit_logs
                WHERE action IN {AR_ACTIONS}
            """))).first()
            students = (await session.execute(text(
                "SELECT COUNT(*) AS n FROM users WHERE is_admin = FALSE OR is_admin IS NULL"
            ))).first()
            await _ensure_table(session)
            wallets = (await session.execute(text(
                "SELECT COALESCE(SUM(gift_cards), 0) AS gift, COALESCE(SUM(default_cards), 0) AS dflt FROM wildcard_wallets"
            ))).first()
        sessions = row.sessions or 0
        return {
            "players": row.players or 0,
            "students": students.n if students else 0,
            "sessions": sessions,
            "play_seconds": _num(row.play_seconds) or 0,
            "avg_session_seconds": _num(row.play_seconds / sessions) if sessions else 0,
            "levels_passed": row.levels_passed or 0,
            "levels_skipped": row.levels_skipped or 0,
            "finished_players": row.finished_players or 0,
            "parts_discovered": row.parts_discovered or 0,
            "sessions_3d": row.sessions_3d or 0,
            "wildcards_used": row.wildcards_used or 0,
            "power_jumps": row.power_jumps or 0,
            "cards_spent": row.cards_spent or 0,
            "back_used": row.back_used or 0,
            "admin_given": row.admin_given or 0,
            "daily_given": row.daily_given or 0,
            "earned": row.earned or 0,
            "cards_in_hand_gift": wallets.gift or 0,
            "cards_in_hand_default": wallets.dflt or 0,
            "players_24h": row.players_24h or 0,
            "last_activity": row.last_activity.isoformat() if row.last_activity else None,
            "level_count": len(LEVEL_NAMES),
        }

    @staticmethod
    async def get_levels() -> List[dict[str, Any]]:
        """Per level: how many players reached it, passed it on their own, skipped it, and how long it took."""
        async with db.get_session() as session:
            rows = (await session.execute(text(f"""
                SELECT
                    {LEVEL} AS level,
                    COUNT(DISTINCT user_id)                                                          AS reached,
                    COUNT(DISTINCT user_id) FILTER (WHERE action = 'ar_stage_completed' AND NOT {SKIPPED}) AS passed,
                    COUNT(DISTINCT user_id) FILTER (WHERE action = 'ar_stage_completed' AND {SKIPPED})     AS skipped,
                    AVG({DURATION}) FILTER (WHERE action = 'ar_stage_completed' AND NOT {SKIPPED})        AS avg_seconds,
                    MIN({DURATION}) FILTER (WHERE action = 'ar_stage_completed' AND NOT {SKIPPED})        AS best_seconds,
                    COUNT(*) FILTER (WHERE action = 'ar_part_discovered')                                 AS parts_discovered
                FROM audit_logs
                WHERE action IN {AR_ACTIONS} AND {LEVEL} IS NOT NULL
                GROUP BY 1
            """))).all()
        by_level = {r.level: r for r in rows}
        levels = sorted(set(range(1, len(LEVEL_NAMES) + 1)) | set(by_level))
        out = []
        for lv in levels:
            r = by_level.get(lv)
            out.append({
                "level": lv,
                "name": _level_name(lv),
                "reached": r.reached if r else 0,
                "passed": r.passed if r else 0,
                "skipped": r.skipped if r else 0,
                "avg_seconds": _num(r.avg_seconds) if r else None,
                "best_seconds": _num(r.best_seconds) if r else None,
                "parts_discovered": r.parts_discovered if r else 0,
            })
        return out

    @staticmethod
    async def get_players(search: str = "") -> List[dict[str, Any]]:
        """One row per learner who has played: which levels they passed or skipped, time played, finished or not."""
        async with db.get_session() as session:
            rows = (await session.execute(text(f"""
                SELECT
                    user_id,
                    MAX(username)                                                                   AS username,
                    COUNT(DISTINCT details->>'session_id')                                          AS sessions,
                    COALESCE(SUM({DURATION}) FILTER (WHERE action = 'ar_session_end'), 0)           AS play_seconds,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT {LEVEL}) FILTER (WHERE action = 'ar_stage_completed' AND NOT {SKIPPED}), NULL) AS passed_levels,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT {LEVEL}) FILTER (WHERE action = 'ar_stage_completed' AND {SKIPPED}), NULL)     AS skipped_levels,
                    MAX({LEVEL})                                                                    AS highest_level,
                    COUNT(*) FILTER (WHERE action = 'ar_part_discovered')                           AS parts_discovered,
                    BOOL_OR(action = 'ar_session_end' AND details->>'ar' = 'false')                 AS played_3d,
                    MIN(created_at) FILTER (WHERE action = 'ar_journey_completed')                  AS finished_at,
                    COUNT(*) FILTER (WHERE {PAID})                                                  AS wildcards_used,
                    COUNT(*) FILTER (WHERE {PAID} AND details->>'mode' = 'jump')                    AS power_jumps,
                    COALESCE(SUM({COST}), 0)                                                        AS cards_spent,
                    COALESCE(SUM({AMOUNT.format('from_gift')}) FILTER (WHERE {PAID}), 0)                 AS spent_gift,
                    COALESCE(SUM({AMOUNT.format('from_default')}) FILTER (WHERE {PAID}), 0)              AS spent_default,
                    COUNT(*) FILTER (WHERE action = 'ar_previous_used')                             AS back_used,
                    COALESCE(SUM({AMOUNT.format('amount')}) FILTER (WHERE action = 'wildcards_granted'), 0) AS admin_given,
                    COALESCE(SUM({AMOUNT.format('added')}) FILTER (WHERE action = 'wildcard_daily_gift'), 0)         AS daily_given,
                    COUNT(*) FILTER (WHERE action = 'wildcard_earned')                           AS earned,
                    (ARRAY_AGG({NOW_LEVEL} ORDER BY created_at DESC, {NOW_LEVEL} DESC) FILTER (WHERE {NOW_LEVEL} IS NOT NULL))[1] AS current_level,
                    MIN(created_at)                                                                 AS first_played,
                    MAX(created_at)                                                                 AS last_played
                FROM audit_logs
                WHERE action IN {AR_ACTIONS}
                  AND (:search = '' OR username ILIKE '%' || :search || '%')
                GROUP BY user_id
                ORDER BY MAX(created_at) DESC
                LIMIT 500
            """), {"search": search.strip()})).all()
            await _ensure_table(session)
            wallets = {w.user_id: w for w in (await session.execute(text(
                "SELECT user_id, gift_cards, default_cards, last_gift_at, unseen FROM wildcard_wallets"
            ))).all()}
        players = []
        for r in rows:
            passed = sorted(r.passed_levels or [])
            skipped = sorted(set(r.skipped_levels or []) - set(passed))
            w = wallets.get(r.user_id)
            players.append({
                "user_id": r.user_id,
                "username": r.username or "unknown",
                "sessions": r.sessions or 0,
                "play_seconds": _num(r.play_seconds) or 0,
                "passed_levels": passed,
                "skipped_levels": skipped,
                "levels_done": len(set(passed) | set(skipped)),
                "highest_level": r.highest_level,
                "current_level": r.current_level,
                "current_level_name": _level_name(r.current_level),
                "parts_discovered": r.parts_discovered or 0,
                "played_3d": bool(r.played_3d),
                "wildcards_used": r.wildcards_used or 0,
                "power_jumps": r.power_jumps or 0,
                "cards_spent": r.cards_spent or 0,
                "back_used": r.back_used or 0,
                "spent_gift": r.spent_gift or 0,
                "spent_default": r.spent_default or 0,
                "admin_given": r.admin_given or 0,
                "daily_given": r.daily_given or 0,
                "earned": r.earned or 0,
                # wallet as stored; the gateway adds the daily gift when the learner next opens the app
                "wallet_gift": w.gift_cards if w else None,
                "wallet_default": w.default_cards if w else None,
                "wallet_total": (w.gift_cards + w.default_cards) if w else None,
                "next_daily_gift": (w.last_gift_at + timedelta(hours=24)).isoformat() if w and w.last_gift_at else None,
                "not_announced": w.unseen if w else 0,
                "finished": r.finished_at is not None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "first_played": r.first_played.isoformat() if r.first_played else None,
                "last_played": r.last_played.isoformat() if r.last_played else None,
            })
        return players

    @staticmethod
    async def get_player_events(user_id: str, limit: int = 300) -> List[dict[str, Any]]:
        """Timeline of one learner's AR events, newest first."""
        async with db.get_session() as session:
            rows = (await session.execute(text(f"""
                SELECT action, details, created_at
                FROM audit_logs
                WHERE user_id = :uid AND action IN {AR_ACTIONS}
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"uid": user_id, "limit": limit})).all()
        return [
            {"action": r.action, "details": r.details or {}, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ]

    @staticmethod
    async def grant_wildcards(user_id: str, amount: int, admin_username: str, request_key: Optional[str] = None,
                              admin: Any = None) -> Optional[dict[str, Any]]:
        """
        Give a learner wildcards (never take). They go to the default cards; the game shows them within
        30 s if it is open, otherwise the next time AR opens. Returns None when the learner does not exist.

        request_key: one key per "Give" form; sending the same key again (double click, retry) returns the first
        result instead of giving the cards twice. Every grant is a wildcard_ledger row ('admin_grant', ref = admin)
        and an admin_audit_log row, in the same transaction as the wallet change.
        """
        if not 1 <= int(amount) <= MAX_GIFT:
            raise HTTPException(status_code=400, detail=f"Give 1 to {MAX_GIFT} wildcards")
        ledger_key = f"admin_grant:{request_key}" if request_key else None
        async with db.get_session() as session:
            user = (await session.execute(
                text("SELECT username, COALESCE(is_admin, FALSE) AS is_admin FROM users WHERE user_id::text = :uid"),
                {"uid": str(user_id)}
            )).first()
            if not user:
                return None
            if user.is_admin:
                raise HTTPException(status_code=409, detail="Administrator accounts have no wildcards")
            await _ensure_table(session)
            if ledger_key:
                await session.execute(text("SELECT 1 AS locked FROM pg_advisory_xact_lock(hashtext(CAST(:k AS TEXT)))"),
                                      {"k": ledger_key})
                done = (await session.execute(text(
                    "SELECT delta FROM wildcard_ledger WHERE idempotency_key = CAST(:k AS TEXT)"), {"k": ledger_key})).first()
                if done:
                    w = (await session.execute(text(
                        "SELECT gift_cards, default_cards FROM wildcard_wallets WHERE user_id = CAST(:uid AS TEXT)"),
                        {"uid": str(user_id)})).first()
                    return {"user_id": str(user_id), "username": user.username, "amount": done.delta, "duplicate": True,
                            "gift": w.gift_cards, "default": w.default_cards, "total": w.gift_cards + w.default_cards}
            w = (await session.execute(text("""
                INSERT INTO wildcard_wallets (user_id, default_cards, unseen)
                VALUES (CAST(:uid AS TEXT), CAST(:first AS INT), CAST(:amount AS INT))
                ON CONFLICT (user_id) DO UPDATE
                    SET default_cards = wildcard_wallets.default_cards + CAST(:amount AS INT),
                        unseen = wildcard_wallets.unseen + CAST(:amount AS INT), updated_at = now()
                RETURNING gift_cards, default_cards
            """), {"uid": str(user_id), "amount": amount, "first": START_CARDS + amount})).first()
            await session.execute(text("""
                INSERT INTO wildcard_ledger (user_id, delta, reason, ref, idempotency_key, gift_after, default_after)
                VALUES (CAST(:u AS TEXT), CAST(:d AS INT), 'admin_grant', CAST(:by AS TEXT), CAST(:k AS TEXT),
                        CAST(:g AS INT), CAST(:df AS INT))
            """), {"u": str(user_id), "d": amount, "by": admin_username, "k": ledger_key,
                   "g": w.gift_cards, "df": w.default_cards})
            await admin_audit.record(session, admin, "wildcards_granted", str(user_id), {
                "amount": amount, "gift_after": w.gift_cards, "default_after": w.default_cards, "by": admin_username})
        wallet = {"gift": w.gift_cards, "default": w.default_cards, "total": w.gift_cards + w.default_cards}
        try:
            r = await get_redis()
            await r.rpush("raw_audit_logs", json.dumps({
                "action": "wildcards_granted",
                "user_id": user_id,
                "username": user.username,
                "details": {"amount": amount, "by": admin_username, **wallet},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass    # the cards are saved; only the log line is missing
        return {"user_id": user_id, "username": user.username, "amount": amount, "duplicate": False, **wallet}
