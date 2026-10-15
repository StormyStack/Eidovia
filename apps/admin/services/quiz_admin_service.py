"""
DNA quiz in the admin panel: access requests (approve / reject), quiz logs, per-user performance and the
overall summary. The tables are created by the gateway (migration 010_quiz.sql); until then every list is empty.

Inclusion rules (the same everywhere): results and averages use COMPLETED attempts only. Abandoned and
expired attempts are listed separately and only count in "completion rate" = completed / ended attempts.
Percentages are compared (not raw scores), so quiz versions with a different number of questions mix fairly.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text

from db import db
from redis_client import get_redis

DEFAULT_WINDOW_HOURS = 24
MAX_WINDOW_DAYS = 7
DEFAULT_COOLDOWN_HOURS = 12
BUCKETS = [("0-49%", 0, 50), ("50-69%", 50, 70), ("70-89%", 70, 90), ("90-100%", 90, 101)]


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


def _num(v) -> Optional[float]:
    return None if v is None else round(float(v), 2)


def _trend(percents: list) -> Optional[str]:
    """Same formula as the app dashboard: mean of the last 3 vs the 3 before; ±5 points."""
    pct = [float(p) for p in (percents or []) if p is not None]
    if len(pct) < 4:
        return None
    recent, before = pct[:3], pct[3:6]
    diff = sum(recent) / len(recent) - sum(before) / len(before)
    return "improving" if diff >= 5 else "declining" if diff <= -5 else "steady"


def _page(page: int, page_size: int) -> tuple[int, int]:
    page_size = max(1, min(page_size, 100))
    return page_size, (max(1, page) - 1) * page_size


def _parse_time(value: Optional[str], name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name}: use an ISO date-time")
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


async def _ready(session) -> bool:
    row = (await session.execute(text("SELECT to_regclass('public.quiz_attempts') IS NOT NULL AS ok"))).first()
    return bool(row and row.ok)


async def _expire(session) -> None:
    await session.execute(text(
        "UPDATE quiz_attempts SET status = 'expired', ended_at = expires_at WHERE status = 'in_progress' AND expires_at <= now()"))
    await session.execute(text(
        "UPDATE quiz_access_requests SET status = 'expired' WHERE status = 'approved' AND window_end <= now()"))


def _request(r) -> dict:
    return {
        "request_id": str(r.request_id), "user_id": r.user_id, "username": r.username, "status": r.status,
        "reason": r.reason, "created_at": _iso(r.created_at), "decided_at": _iso(r.decided_at),
        "decided_by": r.decided_by, "decision_reason": r.decision_reason,
        "window_start": _iso(r.window_start), "window_end": _iso(r.window_end), "cooldown_hours": r.cooldown_hours,
        "used_at": _iso(r.used_at), "used_attempt_id": str(r.used_attempt_id) if r.used_attempt_id else None,
    }


def _attempt_row(a) -> dict:
    return {
        "attempt_id": str(a.attempt_id), "user_id": a.user_id, "username": a.username,
        "attempt_type": a.attempt_type, "status": a.status, "quiz_version": a.quiz_version,
        "started_at": _iso(a.started_at), "ended_at": _iso(a.ended_at), "score": a.score, "total": a.total,
        "percent": _num(a.percent), "duration_s": a.duration_s, "wildcards_spent": a.wildcards_spent,
    }


async def _audit(session, admin, action: str, target_user: str, target_id: str, details: dict) -> None:
    await session.execute(text("""
        INSERT INTO admin_audit_log (admin_user_id, admin_username, action, target_user_id, target_id, details)
        VALUES (CAST(:aid AS TEXT), CAST(:an AS TEXT), CAST(:act AS TEXT), CAST(:tu AS TEXT), CAST(:tid AS TEXT),
                CAST(:d AS JSONB))
    """), {"aid": str(admin.user_id), "an": admin.username, "act": action, "tu": target_user, "tid": target_id,
           "d": json.dumps(details)})


async def _user_event(action: str, user_id: str, username: str, details: dict) -> None:
    """Shows the decision in the learner's history / live audit stream (via the logger)."""
    try:
        r = await get_redis()
        await r.rpush("raw_audit_logs", json.dumps({
            "action": action, "user_id": user_id, "username": username, "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
    except Exception:
        pass


REQ_COLS = ("request_id, user_id, username, status, reason, created_at, decided_at, decided_by, decision_reason, "
            "window_start, window_end, cooldown_hours, used_at, used_attempt_id")
ATT_COLS = ("attempt_id, user_id, username, attempt_type, status, quiz_version, started_at, ended_at, score, total, "
            "percent, duration_s, wildcards_spent, access_request_id, expires_at, cooldown_hours")


class QuizAdminService:
    # -------------------------------------------------------------- summary
    @staticmethod
    async def summary() -> dict[str, Any]:
        async with db.get_session() as session:
            if not await _ready(session):
                return {"ready": False}
            await _expire(session)
            a = (await session.execute(text("""
                SELECT count(*) AS started,
                       count(*) FILTER (WHERE status = 'completed')                    AS completed,
                       count(*) FILTER (WHERE status IN ('abandoned', 'expired'))      AS incomplete,
                       count(*) FILTER (WHERE status = 'in_progress')                  AS in_progress,
                       count(DISTINCT user_id)                                         AS participants,
                       count(DISTINCT user_id) FILTER (WHERE status = 'completed')     AS completers,
                       round(avg(percent) FILTER (WHERE status = 'completed'), 2)      AS avg_percent,
                       round(avg(score) FILTER (WHERE status = 'completed'), 2)        AS avg_score,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY percent) FILTER (WHERE status = 'completed') AS median_percent,
                       round(avg(duration_s) FILTER (WHERE status = 'completed'))      AS avg_duration_s,
                       count(*) FILTER (WHERE attempt_type = 'forced')                 AS forced,
                       count(*) FILTER (WHERE attempt_type = 'authorized')             AS authorized,
                       COALESCE(sum(wildcards_spent), 0)                               AS wildcards_spent,
                       count(*) FILTER (WHERE status = 'completed' AND percent < 50)                     AS b0,
                       count(*) FILTER (WHERE status = 'completed' AND percent >= 50 AND percent < 70)   AS b1,
                       count(*) FILTER (WHERE status = 'completed' AND percent >= 70 AND percent < 90)   AS b2,
                       count(*) FILTER (WHERE status = 'completed' AND percent >= 90)                    AS b3,
                       max(ended_at) FILTER (WHERE status = 'completed')               AS last_completed_at
                FROM quiz_attempts
            """))).first()
            req = {r.status: r.n for r in (await session.execute(text(
                "SELECT status, count(*) AS n FROM quiz_access_requests GROUP BY status"))).all()}
            students = (await session.execute(text(
                "SELECT count(*) AS n FROM users WHERE is_admin = FALSE OR is_admin IS NULL"))).first()
        ended = (a.completed or 0) + (a.incomplete or 0)
        return {
            "ready": True,
            "started_attempts": a.started, "completed_attempts": a.completed, "incomplete_attempts": a.incomplete,
            "in_progress": a.in_progress, "participants": a.participants, "completers": a.completers,
            "students": students.n if students else 0,
            "participation_percent": round(100 * a.completers / students.n, 1) if students and students.n else None,
            "completion_rate": round(100 * a.completed / ended, 1) if ended else None,
            "avg_percent": _num(a.avg_percent), "median_percent": _num(a.median_percent), "avg_score": _num(a.avg_score),
            "avg_duration_s": int(a.avg_duration_s) if a.avg_duration_s is not None else None,
            "forced_attempts": a.forced, "authorized_attempts": a.authorized, "wildcards_spent": int(a.wildcards_spent),
            "distribution": [{"label": lbl, "count": getattr(a, f"b{i}")} for i, (lbl, _lo, _hi) in enumerate(BUCKETS)],
            "requests": {s: req.get(s, 0) for s in ("pending", "approved", "rejected", "used", "expired")},
            "last_completed_at": _iso(a.last_completed_at),
        }

    # -------------------------------------------------------------- access requests
    @staticmethod
    async def list_requests(status: str = "", user: str = "", date_from: str = "", date_to: str = "",
                            page: int = 1, page_size: int = 25) -> dict[str, Any]:
        size, offset = _page(page, page_size)
        df, dt = _parse_time(date_from, "date_from"), _parse_time(date_to, "date_to")
        async with db.get_session() as session:
            if not await _ready(session):
                return {"items": [], "total": 0, "page": page, "page_size": size}
            await _expire(session)
            where = """WHERE (CAST(:st AS TEXT) = '' OR status = CAST(:st AS TEXT))
                         AND (CAST(:u AS TEXT) = '' OR username ILIKE '%' || CAST(:u AS TEXT) || '%' OR user_id = CAST(:u AS TEXT))
                         AND (CAST(:df AS TIMESTAMPTZ) IS NULL OR created_at >= CAST(:df AS TIMESTAMPTZ))
                         AND (CAST(:dt AS TIMESTAMPTZ) IS NULL OR created_at < CAST(:dt AS TIMESTAMPTZ))"""
            params = {"st": status, "u": user.strip(), "df": df, "dt": dt}
            total = (await session.execute(text(f"SELECT count(*) AS n FROM quiz_access_requests {where}"), params)).first().n
            rows = (await session.execute(text(f"""
                SELECT {REQ_COLS} FROM quiz_access_requests {where}
                ORDER BY (status = 'pending') DESC, created_at DESC LIMIT CAST(:lim AS INT) OFFSET CAST(:off AS INT)
            """), {**params, "lim": size, "off": offset})).all()
        return {"items": [_request(r) for r in rows], "total": total, "page": page, "page_size": size}

    @staticmethod
    async def decide(request_id: str, admin, approve: bool, reason: Optional[str], window_start: Optional[str] = None,
                     window_end: Optional[str] = None, cooldown_hours: Optional[int] = None) -> dict[str, Any]:
        """
        Approve: authorizes ONE quiz start inside [window_start, window_end) (default: now → +24 h, at most 7 days)
        with its own cooldown afterwards (default 12 h). Reject: a reason is required. Only pending requests.
        """
        try:
            uuid.UUID(request_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Request not found")
        reason = (reason or "").strip()
        if not approve and len(reason) < 3:
            raise HTTPException(status_code=400, detail="Write a reason for rejecting (at least 3 characters)")
        async with db.get_session() as session:
            if not await _ready(session):
                raise HTTPException(status_code=404, detail="Request not found")
            await _expire(session)
            r = (await session.execute(text(f"""
                SELECT {REQ_COLS}, now() AS now FROM quiz_access_requests WHERE request_id = CAST(:id AS UUID) FOR UPDATE
            """), {"id": request_id})).first()
            if r is None:
                raise HTTPException(status_code=404, detail="Request not found")
            if r.status != "pending":
                raise HTTPException(status_code=409, detail=f"This request is already {r.status}")
            if approve:
                start = _parse_time(window_start, "window_start") or r.now
                end = _parse_time(window_end, "window_end") or (start + timedelta(hours=DEFAULT_WINDOW_HOURS))
                cooldown = DEFAULT_COOLDOWN_HOURS if cooldown_hours is None else int(cooldown_hours)
                if end <= start:
                    raise HTTPException(status_code=400, detail="The window must end after it starts")
                if end <= r.now:
                    raise HTTPException(status_code=400, detail="The window is already over")
                if end - start > timedelta(days=MAX_WINDOW_DAYS):
                    raise HTTPException(status_code=400, detail=f"The window can be at most {MAX_WINDOW_DAYS} days")
                if not 0 <= cooldown <= 168:
                    raise HTTPException(status_code=400, detail="Cooldown must be 0 to 168 hours")
                other = (await session.execute(text("""
                    SELECT 1 FROM quiz_access_requests WHERE user_id = :u AND status = 'approved' AND request_id <> CAST(:id AS UUID)
                """), {"u": r.user_id, "id": request_id})).first()
                if other:
                    raise HTTPException(status_code=409, detail="This learner already has an approved, unused attempt")
                row = (await session.execute(text(f"""
                    UPDATE quiz_access_requests
                    SET status = 'approved', decided_at = now(), decided_by = CAST(:by AS TEXT), decision_reason = CAST(:why AS TEXT),
                        window_start = CAST(:ws AS TIMESTAMPTZ), window_end = CAST(:we AS TIMESTAMPTZ), cooldown_hours = CAST(:cd AS INT)
                    WHERE request_id = CAST(:id AS UUID) AND status = 'pending'
                    RETURNING {REQ_COLS}
                """), {"by": admin.username, "why": reason or None, "ws": start, "we": end, "cd": cooldown, "id": request_id})).first()
                details = {"request_id": request_id, "window_start": _iso(start), "window_end": _iso(end),
                           "cooldown_hours": cooldown, "reason": reason or None, "by": admin.username}
            else:
                row = (await session.execute(text(f"""
                    UPDATE quiz_access_requests
                    SET status = 'rejected', decided_at = now(), decided_by = CAST(:by AS TEXT), decision_reason = CAST(:why AS TEXT)
                    WHERE request_id = CAST(:id AS UUID) AND status = 'pending'
                    RETURNING {REQ_COLS}
                """), {"by": admin.username, "why": reason, "id": request_id})).first()
                details = {"request_id": request_id, "reason": reason, "by": admin.username}
            action = "quiz_access_approved" if approve else "quiz_access_rejected"
            await _audit(session, admin, action, r.user_id, request_id, details)
            await session.commit()          # the admin DB session never commits on its own
        await _user_event(action, r.user_id, r.username, details)
        return _request(row)

    # -------------------------------------------------------------- quiz log
    @staticmethod
    async def list_attempts(user: str = "", date_from: str = "", date_to: str = "", min_percent: Optional[float] = None,
                            max_percent: Optional[float] = None, attempt_type: str = "", status: str = "completed",
                            page: int = 1, page_size: int = 25) -> dict[str, Any]:
        """Completed results by default (status=completed); status=incomplete lists abandoned + expired."""
        size, offset = _page(page, page_size)
        df, dt = _parse_time(date_from, "date_from"), _parse_time(date_to, "date_to")
        statuses = {"completed": ["completed"], "incomplete": ["abandoned", "expired"], "abandoned": ["abandoned"],
                    "expired": ["expired"], "in_progress": ["in_progress"],
                    "all": ["completed", "abandoned", "expired", "in_progress"]}.get(status or "completed")
        if statuses is None:
            raise HTTPException(status_code=400, detail="Unknown status filter")
        async with db.get_session() as session:
            if not await _ready(session):
                return {"items": [], "total": 0, "page": page, "page_size": size}
            await _expire(session)
            where = """WHERE status = ANY(CAST(:sts AS TEXT[]))
                         AND (CAST(:u AS TEXT) = '' OR username ILIKE '%' || CAST(:u AS TEXT) || '%' OR user_id = CAST(:u AS TEXT))
                         AND (CAST(:t AS TEXT) = '' OR attempt_type = CAST(:t AS TEXT))
                         AND (CAST(:df AS TIMESTAMPTZ) IS NULL OR COALESCE(ended_at, started_at) >= CAST(:df AS TIMESTAMPTZ))
                         AND (CAST(:dt AS TIMESTAMPTZ) IS NULL OR COALESCE(ended_at, started_at) < CAST(:dt AS TIMESTAMPTZ))
                         AND (CAST(:minp AS NUMERIC) IS NULL OR percent >= CAST(:minp AS NUMERIC))
                         AND (CAST(:maxp AS NUMERIC) IS NULL OR percent <= CAST(:maxp AS NUMERIC))"""
            params = {"sts": statuses, "u": user.strip(), "t": attempt_type, "df": df, "dt": dt,
                      "minp": min_percent, "maxp": max_percent}
            total = (await session.execute(text(f"SELECT count(*) AS n FROM quiz_attempts {where}"), params)).first().n
            rows = (await session.execute(text(f"""
                SELECT {ATT_COLS} FROM quiz_attempts {where}
                ORDER BY COALESCE(ended_at, started_at) DESC, attempt_id LIMIT CAST(:lim AS INT) OFFSET CAST(:off AS INT)
            """), {**params, "lim": size, "off": offset})).all()
        return {"items": [_attempt_row(r) for r in rows], "total": total, "page": page, "page_size": size}

    @staticmethod
    async def attempt_detail(attempt_id: str) -> dict[str, Any]:
        """Full record. Shows which questions were right or wrong, never the answer key itself."""
        try:
            uuid.UUID(attempt_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Attempt not found")
        async with db.get_session() as session:
            if not await _ready(session):
                raise HTTPException(status_code=404, detail="Attempt not found")
            a = (await session.execute(text(f"""
                SELECT {ATT_COLS}, answers, results FROM quiz_attempts WHERE attempt_id = CAST(:id AS UUID)
            """), {"id": attempt_id})).first()
            if a is None:
                raise HTTPException(status_code=404, detail="Attempt not found")
            v = (await session.execute(text(
                "SELECT questions FROM quiz_versions WHERE quiz_id = 'dna' AND version = CAST(:v AS INT)"
            ), {"v": a.quiz_version})).first()
            req = None
            if a.access_request_id:
                req = (await session.execute(text(f"SELECT {REQ_COLS} FROM quiz_access_requests WHERE request_id = CAST(:r AS UUID)"),
                                             {"r": str(a.access_request_id)})).first()
        questions = (v.questions if isinstance(v.questions, list) else json.loads(v.questions)) if v else []
        answers = a.answers if isinstance(a.answers, dict) else json.loads(a.answers or "{}")
        results = a.results if isinstance(a.results, dict) else json.loads(a.results or "{}")
        out = _attempt_row(a)
        out.update(expires_at=_iso(a.expires_at), cooldown_hours=a.cooldown_hours,
                   authorization=_request(req) if req else None,
                   questions=[{"id": q["id"], "level": q["level"], "text": q["text"], "answer": answers.get(q["id"]),
                               "correct": results.get(q["id"])} for q in questions])
        return out

    # -------------------------------------------------------------- per-user performance
    @staticmethod
    async def list_users(search: str = "", page: int = 1, page_size: int = 25) -> dict[str, Any]:
        size, offset = _page(page, page_size)
        async with db.get_session() as session:
            if not await _ready(session):
                return {"items": [], "total": 0, "page": page, "page_size": size}
            await _expire(session)
            base = """
                WITH a AS (
                    SELECT user_id, max(username) AS username, count(*) AS attempts,
                           count(*) FILTER (WHERE status = 'completed') AS completed,
                           count(*) FILTER (WHERE status IN ('abandoned', 'expired')) AS incomplete,
                           count(*) FILTER (WHERE attempt_type = 'forced') AS forced,
                           count(*) FILTER (WHERE attempt_type = 'authorized') AS authorized,
                           COALESCE(sum(wildcards_spent), 0) AS wildcards_spent,
                           (array_agg(started_at + make_interval(hours => cooldown_hours) ORDER BY started_at DESC))[1] AS next_at,
                           array_agg(percent ORDER BY ended_at DESC) FILTER (WHERE status = 'completed') AS last6
                    FROM quiz_attempts GROUP BY user_id
                )
                SELECT a.*, p.best_percent, p.avg_percent, p.recent_avg_percent, p.percent_stddev, p.latest_score,
                       p.latest_total, p.latest_percent, p.last_completed_at, p.ranking_score_v1, now() AS now
                FROM a LEFT JOIN quiz_user_performance_v1 p ON p.user_id = a.user_id
                WHERE (CAST(:s AS TEXT) = '' OR a.username ILIKE '%' || CAST(:s AS TEXT) || '%' OR a.user_id = CAST(:s AS TEXT))
            """
            params = {"s": search.strip()}
            total = (await session.execute(text(f"SELECT count(*) AS n FROM ({base}) x"), params)).first().n
            rows = (await session.execute(text(f"""
                {base} ORDER BY p.last_completed_at DESC NULLS LAST, a.user_id LIMIT CAST(:lim AS INT) OFFSET CAST(:off AS INT)
            """), {**params, "lim": size, "off": offset})).all()
        return {"items": [QuizAdminService._user_row(r) for r in rows], "total": total, "page": page, "page_size": size}

    @staticmethod
    def _user_row(r) -> dict:
        ended = (r.completed or 0) + (r.incomplete or 0)
        next_at = r.next_at if r.next_at and r.next_at > r.now else None
        return {
            "user_id": r.user_id, "username": r.username, "attempts": r.attempts, "completed": r.completed,
            "incomplete": r.incomplete, "completion_rate": round(100 * r.completed / ended, 1) if ended else None,
            "latest_score": r.latest_score, "latest_total": r.latest_total, "latest_percent": _num(r.latest_percent),
            "best_percent": _num(r.best_percent), "avg_percent": _num(r.avg_percent),
            "recent_avg_percent": _num(r.recent_avg_percent), "percent_stddev": _num(r.percent_stddev),
            "trend": _trend(list(r.last6 or [])[:6]), "last_completed_at": _iso(r.last_completed_at),
            "next_eligible_at": _iso(next_at),
            "cooldown_remaining_s": int((next_at - r.now).total_seconds()) if next_at else 0,
            "forced_attempts": r.forced, "authorized_attempts": r.authorized, "wildcards_spent": int(r.wildcards_spent),
            "ranking_score_v1": _num(r.ranking_score_v1),
        }

    @staticmethod
    async def user_detail(user_id: str) -> dict[str, Any]:
        page = await QuizAdminService.list_users(search=user_id, page=1, page_size=1)
        item = next((i for i in page["items"] if i["user_id"] == user_id), None)
        async with db.get_session() as session:
            if not await _ready(session):
                return {"user_id": user_id, "summary": None, "attempts": [], "requests": []}
            attempts = (await session.execute(text(f"""
                SELECT {ATT_COLS} FROM quiz_attempts WHERE user_id = :u ORDER BY started_at DESC LIMIT 50
            """), {"u": user_id})).all()
            reqs = (await session.execute(text(f"""
                SELECT {REQ_COLS} FROM quiz_access_requests WHERE user_id = :u ORDER BY created_at DESC LIMIT 20
            """), {"u": user_id})).all()
        return {"user_id": user_id, "summary": item, "attempts": [_attempt_row(a) for a in attempts],
                "requests": [_request(r) for r in reqs]}
