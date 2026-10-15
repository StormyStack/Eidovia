"""
Admin Center accounts: the Users section (app learners only) and the Administrators section (admin accounts only),
a learner's profile, wildcard history and activity log.

Who is who comes from the data model, never from names: users.is_admin = TRUE → Administrators, otherwise Users.
(The model has one administrative role today, "Admin", with full rights. More roles can be added later as a column.)

The activity log is audit_logs, the table the logger service fills: every event the gateway records (sign-up,
login, failed login, logout, app opened, profile and password changes, AI questions, AR game, wildcards, quiz)
plus the administrators' actions on the account ("by" = the admin). IP address and device are added on the server
from the request (gateway request_log), timestamps by the server. Nothing here can edit or delete those records.
"""

import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text

from db import db
from services.tech_service import TechService
from services.user_log_service import UserLogService

ACCOUNT_ACTIONS = ("register", "login", "login_failed", "logout", "app_open", "profile_updated", "password_changed",
                   "password_reset_requested", "password_reset_by_admin", "account_updated_by_admin")

# one place for "what kind of activity is this" and "did it work" (used for filters and the Status column)
CATEGORY_SQL = f"""CASE
    WHEN action IN ({", ".join(f"'{a}'" for a in ACCOUNT_ACTIONS)}) THEN 'account'
    WHEN action = 'message_sent' THEN 'chat'
    WHEN action LIKE 'ar\\_%' THEN 'ar'
    WHEN action LIKE 'wildcard%' THEN 'wildcard'
    WHEN action LIKE 'quiz\\_%' THEN 'quiz'
    ELSE 'other' END"""
STATUS_SQL = """CASE
    WHEN action = 'login_failed' THEN 'failed'
    WHEN action = 'wildcard_used' AND details->>'paid' = 'false' THEN 'failed'
    WHEN action = 'message_sent' AND details->>'fallback' = 'true' THEN 'failed'
    ELSE 'success' END"""
CATEGORIES = {"account", "chat", "ar", "wildcard", "quiz", "other", "admin"}


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


def _uuid(user_id: str) -> str:
    try:
        return str(uuid.UUID(user_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")


def _page(page: int, page_size: int) -> tuple[int, int]:
    size = max(1, min(page_size, 100))
    return size, (max(1, page) - 1) * size


async def _has_table(session, name: str) -> bool:
    row = (await session.execute(text("SELECT to_regclass(CAST(:t AS TEXT)) IS NOT NULL AS ok"), {"t": f"public.{name}"})).first()
    return bool(row and row.ok)


class AccountService:
    # ------------------------------------------------------------------ lists
    @staticmethod
    async def list_accounts(admins: bool, q: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """Users section (admins=False) or Administrators section (admins=True), newest first, paginated."""
        size, offset = _page(page, page_size)
        async with db.get_session() as session:
            wallets = await _has_table(session, "wildcard_wallets")
            where = """WHERE COALESCE(u.is_admin, FALSE) = CAST(:adm AS BOOLEAN)
                         AND (CAST(:q AS TEXT) = '' OR lower(u.username) LIKE CAST(:like AS TEXT)
                              OR lower(COALESCE(u.email, '')) LIKE CAST(:like AS TEXT) OR u.user_id::text = CAST(:q AS TEXT))"""
            params = {"adm": admins, "q": q.strip(), "like": f"%{q.strip().lower()}%"}
            total = (await session.execute(text(f"SELECT count(*) AS n FROM users u {where}"), params)).first().n
            wallet_cols = ("w.gift_cards + w.default_cards AS wildcards" if wallets else "NULL::int AS wildcards")
            wallet_join = "LEFT JOIN wildcard_wallets w ON w.user_id = u.user_id::text" if wallets else ""
            rows = (await session.execute(text(f"""
                SELECT u.user_id::text AS user_id, u.username, u.email, u.detail_level, u.language, u.created_at,
                       COALESCE(u.is_admin, FALSE) AS is_admin,
                       to_jsonb(u) ->> 'age' AS age, to_jsonb(u) ->> 'gender' AS gender,          -- migration 009
                       (SELECT max(a.created_at) FROM audit_logs a
                         WHERE a.user_id = u.user_id::text AND a.action = 'login') AS last_login,
                       {wallet_cols}
                FROM users u {wallet_join}
                {where}
                ORDER BY u.created_at DESC NULLS LAST, u.user_id
                LIMIT CAST(:lim AS INT) OFFSET CAST(:off AS INT)
            """), {**params, "lim": size, "off": offset})).all()
        online = {o["user_id"]: o for o in await TechService.get_logged_in()}
        items = []
        for r in rows:
            o = online.get(r.user_id)
            items.append({
                "user_id": r.user_id, "username": r.username, "email": r.email, "is_admin": bool(r.is_admin),
                "role": "Admin" if r.is_admin else "User",
                "level": r.detail_level, "language": r.language,
                "age": int(r.age) if r.age else None, "gender": r.gender,
                "registered_at": _iso(r.created_at), "last_login": _iso(r.last_login),
                "wildcards": r.wildcards if not r.is_admin else None,
                "online": o is not None, "active_now": bool(o and o.get("active")),
            })
        return {"items": items, "total": total, "page": max(1, page), "page_size": size}

    # ------------------------------------------------------------------ profile
    @staticmethod
    async def user_profile(user_id: str) -> dict[str, Any]:
        """Everything the Users section shows about one learner (administrator accounts are not served here)."""
        uid = _uuid(user_id)
        summary = await UserLogService.get_summary(uid)
        if summary is None:
            raise HTTPException(status_code=404, detail="User not found")
        if summary["is_admin"]:
            raise HTTPException(status_code=409, detail="This is an administrator account. See Administrators.")
        async with db.get_session() as session:
            language = (await session.execute(text("SELECT language FROM users WHERE user_id::text = :u"),
                                              {"u": uid})).first()
            since = (await session.execute(text("""
                SELECT min(created_at) AS first_event,
                       min(created_at) FILTER (WHERE details ? 'ip') AS first_ip,
                       count(*) AS events
                FROM audit_logs WHERE user_id = :u
            """), {"u": uid})).first()
        quiz = None
        try:
            from services.quiz_admin_service import QuizAdminService
            quiz = (await QuizAdminService.user_detail(uid)).get("summary")
        except Exception:
            quiz = None
        return {**summary, "language": language.language if language else None, "quiz": quiz, "history": {
            "events": since.events, "first_event": _iso(since.first_event), "first_ip": _iso(since.first_ip)}}

    # ------------------------------------------------------------------ wildcards
    @staticmethod
    async def wildcard_history(user_id: str, limit: int = 50) -> dict[str, Any]:
        """Wallet now + the wildcard ledger (every grant, gift, earn and spend since the ledger exists)."""
        uid = _uuid(user_id)
        async with db.get_session() as session:
            user = (await session.execute(text(
                "SELECT username, COALESCE(is_admin, FALSE) AS is_admin FROM users WHERE user_id::text = :u"), {"u": uid})).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            if user.is_admin:
                raise HTTPException(status_code=409, detail="Administrator accounts have no wildcards")
            wallet = None
            if await _has_table(session, "wildcard_wallets"):
                w = (await session.execute(text(
                    "SELECT gift_cards, default_cards, last_gift_at, updated_at FROM wildcard_wallets WHERE user_id = :u"),
                    {"u": uid})).first()
                if w:
                    wallet = {"gift": w.gift_cards, "default": w.default_cards, "total": w.gift_cards + w.default_cards,
                              "last_gift_at": _iso(w.last_gift_at), "updated_at": _iso(w.updated_at)}
            entries, first = [], None
            if await _has_table(session, "wildcard_ledger"):
                rows = (await session.execute(text("""
                    SELECT entry_id, delta, reason, ref, gift_after, default_after, created_at
                    FROM wildcard_ledger WHERE user_id = :u ORDER BY created_at DESC, entry_id DESC LIMIT CAST(:n AS INT)
                """), {"u": uid, "n": limit})).all()
                # not "AS t": row.t is SQLAlchemy's typed-tuple accessor, not the column
                first = (await session.execute(text(
                    "SELECT min(created_at) AS ledger_start FROM wildcard_ledger"))).first().ledger_start
                entries = [{
                    "entry_id": r.entry_id, "delta": r.delta, "reason": r.reason,
                    "by": r.ref if r.reason == "admin_grant" else None,
                    "ref": r.ref if r.reason != "admin_grant" else None,
                    "total_after": (r.gift_after or 0) + (r.default_after or 0) if r.gift_after is not None else None,
                    "created_at": _iso(r.created_at),
                } for r in rows]
        return {"user_id": uid, "username": user.username, "wallet": wallet, "entries": entries,
                "ledger_since": _iso(first)}

    # ------------------------------------------------------------------ activity log
    @staticmethod
    async def activity(user_id: str, page: int = 1, page_size: int = 50, date_from: str = "", date_to: str = "",
                       category: str = "", status: str = "", ip: str = "", q: str = "") -> dict[str, Any]:
        """The user's activity log, newest first, filtered and paginated in the database."""
        uid = _uuid(user_id)
        if category and category not in CATEGORIES:
            raise HTTPException(status_code=400, detail="Unknown activity type")
        if status and status not in ("success", "failed"):
            raise HTTPException(status_code=400, detail="Status must be success or failed")
        df, dt = _time(date_from, "date_from"), _time(date_to, "date_to")
        size, offset = _page(page, page_size)
        base = f"""
            WITH a AS (
                SELECT id, action, details, created_at, {CATEGORY_SQL} AS category, {STATUS_SQL} AS status
                FROM audit_logs WHERE user_id = :u
            )
            SELECT * FROM a
            WHERE (CAST(:cat AS TEXT) = '' OR category = CAST(:cat AS TEXT)
                   OR (CAST(:cat AS TEXT) = 'admin' AND details ? 'by'))
              AND (CAST(:st AS TEXT) = '' OR status = CAST(:st AS TEXT))
              AND (CAST(:ip AS TEXT) = '' OR details->>'ip' LIKE CAST(:ip AS TEXT) || '%')
              AND (CAST(:df AS TIMESTAMPTZ) IS NULL OR created_at >= CAST(:df AS TIMESTAMPTZ))
              AND (CAST(:dt AS TIMESTAMPTZ) IS NULL OR created_at < CAST(:dt AS TIMESTAMPTZ))
              AND (CAST(:q AS TEXT) = '' OR action ILIKE '%' || CAST(:q AS TEXT) || '%'
                   OR details::text ILIKE '%' || CAST(:q AS TEXT) || '%')
        """
        params = {"u": uid, "cat": "" if category == "" else category, "st": status, "ip": ip.strip(),
                  "df": df, "dt": dt, "q": q.strip()}
        async with db.get_session() as session:
            total = (await session.execute(text(f"SELECT count(*) AS n FROM ({base}) x"), params)).first().n
            rows = (await session.execute(text(f"""
                {base} ORDER BY created_at DESC, id LIMIT CAST(:lim AS INT) OFFSET CAST(:off AS INT)
            """), {**params, "lim": size, "off": offset})).all()
        items = []
        for r in rows:
            d = r.details if isinstance(r.details, dict) else {}
            items.append({
                "id": str(r.id), "action": r.action, "category": r.category, "status": r.status,
                "created_at": _iso(r.created_at), "ip": d.get("ip"), "device": d.get("device"),
                "by": d.get("by"), "details": d,
            })
        return {"items": items, "total": total, "page": max(1, page), "page_size": size}


def _time(value: str, name: str):
    from datetime import datetime, timezone
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name}: use an ISO date-time")
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
