"""
User history for support: a summary (sign-up, logins, app use, AI questions, AR game, wildcards, where from)
and the detail log (every stored event plus the user's recent requests to the gateway).
"""

from typing import Any, List, Optional
from sqlalchemy import text

from db import db
from services.tech_service import TechService

DURATION = "(CASE WHEN details->>'duration_s' ~ '^[0-9]+(\\.[0-9]+)?$' THEN (details->>'duration_s')::numeric END)"


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


class UserLogService:
    @staticmethod
    async def get_summary(user_id: str) -> Optional[dict[str, Any]]:
        async with db.get_session() as session:
            user = (await session.execute(text(
                "SELECT user_id::text AS user_id, username, email, is_admin, language, created_at FROM users WHERE user_id::text = :u"
            ), {"u": user_id})).first()
            if not user:
                return None
            t = (await session.execute(text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE action = 'register')                                     AS signups,
                    COUNT(*) FILTER (WHERE action = 'login')                                        AS logins,
                    COUNT(*) FILTER (WHERE action = 'logout')                                       AS logouts,
                    COUNT(*) FILTER (WHERE action = 'app_open')                                     AS app_opens,
                    COUNT(DISTINCT (created_at AT TIME ZONE 'UTC')::date)                           AS active_days,
                    COUNT(*) FILTER (WHERE action = 'message_sent')                                 AS questions,
                    COUNT(*) FILTER (WHERE action = 'message_sent' AND details->>'cached' = 'true') AS questions_cached,
                    COUNT(*) FILTER (WHERE action = 'message_sent' AND details->>'fallback' = 'true') AS questions_failed,
                    COUNT(DISTINCT details->>'session_id') FILTER (WHERE action = 'ar_session_start') AS ar_sessions,
                    COALESCE(SUM({DURATION}) FILTER (WHERE action = 'ar_session_end'), 0)           AS ar_seconds,
                    COUNT(*) FILTER (WHERE action = 'ar_stage_completed' AND details->>'skipped' IS DISTINCT FROM 'true') AS levels_passed,
                    COUNT(*) FILTER (WHERE action = 'ar_journey_completed')                         AS journeys,
                    COUNT(*) FILTER (WHERE action = 'ar_wildcard_used' AND details->>'paid' = 'true') AS wildcards_used,
                    COUNT(*) FILTER (WHERE action = 'ar_previous_used')                             AS back_used,
                    MIN(created_at)                                                                 AS first_activity,
                    MAX(created_at)                                                                 AS last_activity,
                    MAX(created_at) FILTER (WHERE action = 'login')                                 AS last_login,
                    MAX(created_at) FILTER (WHERE action = 'logout')                                AS last_logout,
                    MAX(created_at) FILTER (WHERE action = 'message_sent')                          AS last_question,
                    MAX(created_at) FILTER (WHERE action LIKE 'ar\\_%')                             AS last_ar
                FROM audit_logs WHERE user_id = :u
            """), {"u": user_id})).first()
            ips = (await session.execute(text("""
                SELECT details->>'ip' AS ip, COUNT(*) AS n, MAX(created_at) AS last
                FROM audit_logs WHERE user_id = :u AND details ? 'ip' AND details->>'ip' IS NOT NULL
                GROUP BY 1 ORDER BY MAX(created_at) DESC LIMIT 10
            """), {"u": user_id})).all()
            devices = (await session.execute(text("""
                SELECT details->>'device' AS device, COUNT(*) AS n, MAX(created_at) AS last
                FROM audit_logs WHERE user_id = :u AND details ? 'device' AND details->>'device' IS NOT NULL
                GROUP BY 1 ORDER BY MAX(created_at) DESC LIMIT 5
            """), {"u": user_id})).all()
            try:
                tickets = (await session.execute(text(
                    "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE status <> 'resolved') AS open FROM support_tickets WHERE user_id = :u"
                ), {"u": user_id})).first()
            except Exception:
                tickets = None
            try:
                wallet = (await session.execute(text(
                    "SELECT gift_cards, default_cards FROM ar_wallets WHERE user_id = :u"
                ), {"u": user_id})).first()
            except Exception:
                wallet = None

        online = next((o for o in await TechService.get_logged_in() if o["user_id"] == user_id), None)
        return {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "is_admin": bool(user.is_admin),
            "signed_up_at": _iso(user.created_at),
            "logged_in_now": online is not None,
            "active_now": bool(online and online["active"]),
            "last_seen": online.get("last_seen") if online else None,
            "current_ip": online.get("ip") if online else None,
            "current_device": online.get("device") if online else None,
            "logins": t.logins or 0,
            "logouts": t.logouts or 0,
            "app_opens": t.app_opens or 0,
            "active_days": t.active_days or 0,
            "questions": t.questions or 0,
            "questions_cached": t.questions_cached or 0,
            "questions_failed": t.questions_failed or 0,
            "ar_sessions": t.ar_sessions or 0,
            "ar_seconds": round(float(t.ar_seconds or 0)),
            "levels_passed": t.levels_passed or 0,
            "journeys": t.journeys or 0,
            "wildcards_used": t.wildcards_used or 0,
            "back_used": t.back_used or 0,
            "wallet": ({"gift": wallet.gift_cards, "default": wallet.default_cards,
                        "total": wallet.gift_cards + wallet.default_cards} if wallet else None),
            "tickets": tickets.n if tickets else 0,
            "tickets_open": tickets.open if tickets else 0,
            "first_activity": _iso(t.first_activity),
            "last_activity": _iso(t.last_activity),
            "last_login": _iso(t.last_login),
            "last_logout": _iso(t.last_logout),
            "last_question": _iso(t.last_question),
            "last_ar": _iso(t.last_ar),
            "ips": [{"ip": r.ip, "count": r.n, "last": _iso(r.last)} for r in ips],
            "devices": [{"device": r.device, "count": r.n, "last": _iso(r.last)} for r in devices],
        }

    @staticmethod
    async def get_activity(user_id: str, limit: int = 500, include_requests: bool = True) -> List[dict[str, Any]]:
        """Everything the user did, newest first: stored events (source=event) and gateway requests (source=request)."""
        async with db.get_session() as session:
            rows = (await session.execute(text("""
                SELECT action, username, details, created_at FROM audit_logs
                WHERE user_id = :u ORDER BY created_at DESC LIMIT :limit
            """), {"u": user_id, "limit": limit})).all()
        items = [{"source": "event", "action": r.action, "username": r.username, "details": r.details or {},
                  "created_at": _iso(r.created_at)} for r in rows]
        if include_requests:
            for e in await TechService.requests_for_user(user_id, limit):
                items.append({"source": "request", "action": "request", "details": e, "created_at": e.get("ts")})
        items.sort(key=lambda i: i["created_at"] or "", reverse=True)
        return items[:limit * 2]
