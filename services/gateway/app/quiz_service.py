"""
DNA quiz: business rules (used by routers/quiz.py; the admin panel reads the same tables).

Rules (all decided here, on server time, never on the phone's clock)
  * Cooldown: one attempt every 12 h, counted from the START of the user's latest attempt of any kind.
    Abandoned and expired attempts count too: starting an attempt shows the questions.
    (An admin approval may set its own cooldown for the attempt it authorizes.)
  * An attempt must be submitted within TIME_LIMIT_S (30 min). Later it becomes 'expired' (no result).
  * Force Attempt: only during the cooldown; costs exactly FORCE_COST (3) wildcards, taken in the SAME
    transaction that creates the attempt (wallet row locked, ledger row with a unique idempotency key).
    If anything fails, nothing is taken. Retries with the same idempotency key return the same attempt.
    Forced cards are not refunded when a started attempt is abandoned or expires (the questions were seen).
  * Admin authorization: an approved request allows ONE attempt start inside [window_start, window_end).
    Starting it marks the request 'used' (atomically, row locked). Past window_end it becomes 'expired'.
    A user has at most one pending and at most one approved request (unique partial indexes).
  * Only one attempt can be in progress per user (unique partial index). Every start/submit for a user runs
    under a per-user transaction advisory lock, so simultaneous requests are processed one after another.
  * Scores are computed only here, from the answer key stored in quiz_versions. Submitting a completed
    attempt again returns the stored result (no second result is created).
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text

from app import quiz_content as content
from app.routers.wildcards import deduct, ledger, wallet_for

logger = logging.getLogger(__name__)

QUIZ_ID, QUIZ_VERSION = content.QUIZ_ID, content.QUIZ_VERSION
FORCE_COST = content.FORCE_COST
COOLDOWN_HOURS = content.COOLDOWN_HOURS
LEVELS = {"easy", "medium", "hard"}


class QuizError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


# ============================================================
# SCHEMA (same as migrations/010_quiz.sql; run once per process)
# ============================================================

def _schema_file():
    """services/ai/migrations/010_quiz.sql: the one definition of the quiz tables (also run by Postgres initdb)."""
    import os
    from pathlib import Path
    here = Path(__file__).resolve()
    candidates = [os.getenv("QUIZ_SCHEMA_FILE", ""),
                  here.parents[2] / "ai" / "migrations" / "010_quiz.sql",      # repo layout (tests, local runs)
                  Path("/app/migrations-shared/010_quiz.sql")]                 # docker-compose mount
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("010_quiz.sql not found (mount ./services/ai/migrations at /app/migrations-shared)")


def _schema_statements() -> list[str]:
    lines = [ln for ln in _schema_file().read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


_schema_ready = False


async def ensure_schema(session) -> None:
    """Create the quiz tables if needed and store quiz version 1 (questions + answer key)."""
    global _schema_ready
    if _schema_ready:
        return
    for statement in _schema_statements():
        await session.execute(text(statement))
    await session.execute(text("""
        INSERT INTO quiz_versions (quiz_id, version, title, questions, answer_key, question_count, time_limit_s)
        VALUES (CAST(:q AS TEXT), CAST(:v AS INT), CAST(:t AS TEXT), CAST(:qs AS JSONB), CAST(:ak AS JSONB),
                CAST(:n AS INT), CAST(:tl AS INT))
        ON CONFLICT (quiz_id, version) DO NOTHING
    """), {"q": QUIZ_ID, "v": QUIZ_VERSION, "t": content.QUIZ_TITLE, "qs": json.dumps(content.QUESTIONS),
           "ak": json.dumps(content.ANSWER_KEY), "n": len(content.QUESTIONS), "tl": content.TIME_LIMIT_S})
    _schema_ready = True


# ============================================================
# HELPERS
# ============================================================

def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat() if v else None


async def _lock_user(session, user_id: str) -> None:
    """Serialize all quiz writes of one user (released at commit/rollback)."""
    await session.execute(text("SELECT 1 AS locked FROM pg_advisory_xact_lock(hashtext(CAST(:k AS TEXT)))"),
                          {"k": f"quiz:{user_id}"})


async def _expire_stale(session, user_id: str) -> None:
    """Lazy expiry: unsubmitted attempts past their time limit, approvals past their window."""
    await session.execute(text("""
        UPDATE quiz_attempts SET status = 'expired', ended_at = expires_at
        WHERE user_id = :u AND status = 'in_progress' AND expires_at <= now()
    """), {"u": user_id})
    await session.execute(text("""
        UPDATE quiz_access_requests SET status = 'expired'
        WHERE user_id = :u AND status = 'approved' AND window_end <= now()
    """), {"u": user_id})


async def _version(session, version: int = QUIZ_VERSION):
    row = (await session.execute(text("""
        SELECT quiz_id, version, title, questions, answer_key, question_count, time_limit_s
        FROM quiz_versions WHERE quiz_id = :q AND version = CAST(:v AS INT)
    """), {"q": QUIZ_ID, "v": version})).first()
    if row is None:
        raise QuizError(500, "QUIZ_MISSING", "The quiz is not available.")
    questions = row.questions if isinstance(row.questions, list) else json.loads(row.questions)
    key = row.answer_key if isinstance(row.answer_key, dict) else json.loads(row.answer_key)
    return row, questions, key


async def _cooldown(session, user_id: str) -> dict:
    row = (await session.execute(text("""
        SELECT started_at + make_interval(hours => cooldown_hours) AS next_at, now() AS now
        FROM quiz_attempts WHERE user_id = :u ORDER BY started_at DESC LIMIT 1
    """), {"u": user_id})).first()
    now = row.now if row else (await session.execute(text("SELECT now() AS now"))).first().now
    next_at = row.next_at if row else None
    remaining = max(0, int((next_at - now).total_seconds())) if next_at else 0
    return {"now": now, "next_eligible_at": next_at if remaining else None, "cooldown_remaining_s": remaining,
            "eligible": remaining == 0}


def _request_out(r) -> dict:
    return {
        "request_id": str(r.request_id), "status": r.status, "reason": r.reason,
        "created_at": _iso(r.created_at), "decided_at": _iso(r.decided_at), "decided_by": r.decided_by,
        "decision_reason": r.decision_reason, "window_start": _iso(r.window_start), "window_end": _iso(r.window_end),
        "cooldown_hours": r.cooldown_hours, "used_at": _iso(r.used_at),
        "used_attempt_id": str(r.used_attempt_id) if r.used_attempt_id else None,
    }


REQUEST_COLUMNS = ("request_id, status, reason, created_at, decided_at, decided_by, decision_reason, "
                   "window_start, window_end, cooldown_hours, used_at, used_attempt_id")


def _questions_out(questions: list) -> list:
    return [{"id": q["id"], "level": q["level"], "text": q["text"], "options": q["options"]} for q in questions]


def _result_out(a, questions: Optional[list] = None, key: Optional[dict] = None) -> dict:
    """The result of a completed attempt. The per-question review (with correct answers) only after completion."""
    out = {
        "attempt_id": str(a.attempt_id), "status": a.status, "attempt_type": a.attempt_type,
        "quiz_version": a.quiz_version, "started_at": _iso(a.started_at), "ended_at": _iso(a.ended_at),
        "expires_at": _iso(a.expires_at), "duration_s": a.duration_s, "wildcards_spent": a.wildcards_spent,
        "score": a.score, "total": a.total,
        "correct": a.score, "incorrect": (a.total - a.score) if a.total is not None and a.score is not None else None,
        "percent": float(a.percent) if a.percent is not None else None,
    }
    if a.status == "completed" and questions is not None and key is not None:
        answers = a.answers if isinstance(a.answers, dict) else json.loads(a.answers or "{}")
        out["review"] = [{
            "id": q["id"], "level": q["level"], "text": q["text"], "options": q["options"],
            "your_answer": answers.get(q["id"]), "correct_answer": key[q["id"]]["answer"],
            "correct": answers.get(q["id"]) == key[q["id"]]["answer"], "explanation": key[q["id"]]["explanation"],
        } for q in questions]
    return out


ATTEMPT_COLUMNS = ("attempt_id, user_id, attempt_type, status, quiz_version, started_at, expires_at, ended_at, "
                   "duration_s, score, total, percent, answers, wildcards_spent, access_request_id, cooldown_hours")


# ============================================================
# STATUS
# ============================================================

async def status(session, user_id: str) -> dict:
    """Everything the quiz screen and the dashboard need to decide what to show."""
    await ensure_schema(session)
    await _lock_user(session, user_id)
    await _expire_stale(session, user_id)
    version, questions, _ = await _version(session)
    cd = await _cooldown(session, user_id)
    wallet, _daily = await wallet_for(session, user_id)
    active = (await session.execute(text(f"""
        SELECT {ATTEMPT_COLUMNS} FROM quiz_attempts WHERE user_id = :u AND status = 'in_progress'
    """), {"u": user_id})).first()
    reqs = (await session.execute(text(f"""
        SELECT {REQUEST_COLUMNS} FROM quiz_access_requests WHERE user_id = :u ORDER BY created_at DESC LIMIT 10
    """), {"u": user_id})).all()
    pending = next((r for r in reqs if r.status == "pending"), None)
    approved = next((r for r in reqs if r.status == "approved"), None)
    now = cd["now"]
    auth = None
    if approved is not None:
        auth = {**_request_out(approved), "usable_now": approved.window_start <= now < approved.window_end}
    return {
        "server_time": _iso(now),
        "quiz": {"quiz_id": QUIZ_ID, "version": version.version, "title": version.title,
                 "question_count": version.question_count, "time_limit_s": version.time_limit_s,
                 "cooldown_hours": COOLDOWN_HOURS},
        "eligible": cd["eligible"] and active is None,
        "next_eligible_at": _iso(cd["next_eligible_at"]),
        "cooldown_remaining_s": cd["cooldown_remaining_s"],
        "active_attempt": ({"attempt_id": str(active.attempt_id), "attempt_type": active.attempt_type,
                            "started_at": _iso(active.started_at), "expires_at": _iso(active.expires_at)}
                           if active else None),
        "force_cost": FORCE_COST,
        "wildcards": wallet["total"],
        "can_force": active is None and not cd["eligible"] and wallet["total"] >= FORCE_COST,
        "authorization": auth,
        "pending_request": _request_out(pending) if pending else None,
        "can_request": pending is None and approved is None,
        "requests": [_request_out(r) for r in reqs],
        "_daily_gift": _daily,
        "_wallet": wallet,
    }


# ============================================================
# START
# ============================================================

async def start(session, user_id: str, username: str, mode: str, key: str) -> tuple[dict, dict]:
    """
    Start an attempt. mode: normal | forced | authorized. key: client idempotency key (retries return the
    same attempt, never a second charge). Returns (response, event details).
    """
    if mode not in ("normal", "forced", "authorized"):
        raise QuizError(400, "VALIDATION_ERROR", "Unknown attempt mode.")
    await ensure_schema(session)
    await _lock_user(session, user_id)
    await _expire_stale(session, user_id)
    version, questions, _ = await _version(session)

    # retry of the same start request → the same attempt
    same = (await session.execute(text(f"""
        SELECT {ATTEMPT_COLUMNS} FROM quiz_attempts WHERE user_id = :u AND start_key = CAST(:k AS TEXT)
    """), {"u": user_id, "k": key})).first()
    if same is not None:
        if same.status != "in_progress":
            raise QuizError(409, "ATTEMPT_CLOSED", "This attempt has already ended.", {"attempt_id": str(same.attempt_id)})
        wallet, _ = await wallet_for(session, user_id)
        return _started(same, questions, wallet["total"], replay=True), {}

    active = (await session.execute(text(
        "SELECT attempt_id FROM quiz_attempts WHERE user_id = :u AND status = 'in_progress'"
    ), {"u": user_id})).first()
    if active is not None:
        raise QuizError(409, "ATTEMPT_IN_PROGRESS", "You already have a quiz in progress.",
                        {"attempt_id": str(active.attempt_id)})

    cd = await _cooldown(session, user_id)
    attempt_id = str(uuid.uuid4())
    cooldown_hours, spent, request_id = COOLDOWN_HOURS, 0, None
    wallet, _ = await wallet_for(session, user_id)

    if mode == "normal":
        if not cd["eligible"]:
            raise QuizError(429, "COOLDOWN", "You can take the quiz again after the cooldown.",
                            {"next_eligible_at": _iso(cd["next_eligible_at"]),
                             "cooldown_remaining_s": cd["cooldown_remaining_s"]})
    elif mode == "forced":
        if cd["eligible"]:
            raise QuizError(409, "FORCE_NOT_NEEDED", "No cooldown right now: start a normal attempt (free).")
        if wallet["total"] < FORCE_COST:
            raise QuizError(402, "NOT_ENOUGH_WILDCARDS",
                            f"A forced attempt costs {FORCE_COST} wildcards. You have {wallet['total']}.",
                            {"wildcards": wallet["total"], "force_cost": FORCE_COST})
        await deduct(session, user_id, wallet, FORCE_COST)
        # unique idempotency key: even a bug that reached this line twice could not charge twice
        await ledger(session, user_id, -FORCE_COST, "quiz_force", wallet, ref=attempt_id, key=f"quiz_force:{user_id}:{key}")
        spent = FORCE_COST
    else:  # authorized
        req = (await session.execute(text(f"""
            SELECT {REQUEST_COLUMNS}, now() AS now FROM quiz_access_requests
            WHERE user_id = :u AND status = 'approved' ORDER BY decided_at DESC LIMIT 1 FOR UPDATE
        """), {"u": user_id})).first()
        if req is None:
            raise QuizError(403, "NOT_AUTHORIZED", "You have no approved quiz request.")
        if req.now < req.window_start:
            raise QuizError(403, "NOT_YET", "Your approved attempt has not started yet.",
                            {"window_start": _iso(req.window_start)})
        if cd["eligible"]:
            # keep the approval for later: a normal attempt is free right now
            raise QuizError(409, "AUTH_NOT_NEEDED", "No cooldown right now: start a normal attempt (your approval stays).")
        request_id = str(req.request_id)
        cooldown_hours = req.cooldown_hours if req.cooldown_hours is not None else COOLDOWN_HOURS

    row = (await session.execute(text(f"""
        INSERT INTO quiz_attempts (attempt_id, user_id, username, quiz_id, quiz_version, attempt_type, start_key,
                                   expires_at, cooldown_hours, wildcards_spent, access_request_id)
        VALUES (CAST(:id AS UUID), :u, CAST(:name AS TEXT), :q, CAST(:v AS INT), CAST(:t AS TEXT), CAST(:k AS TEXT),
                now() + make_interval(secs => CAST(:tl AS INT)), CAST(:cd AS INT), CAST(:spent AS INT),
                CAST(:req AS UUID))
        RETURNING {ATTEMPT_COLUMNS}
    """), {"id": attempt_id, "u": user_id, "name": username, "q": QUIZ_ID, "v": version.version, "t": mode,
           "k": key, "tl": version.time_limit_s, "cd": cooldown_hours, "spent": spent, "req": request_id})).first()
    if request_id:
        await session.execute(text("""
            UPDATE quiz_access_requests SET status = 'used', used_at = now(), used_attempt_id = CAST(:a AS UUID)
            WHERE request_id = CAST(:r AS UUID) AND status = 'approved'
        """), {"a": attempt_id, "r": request_id})
    event = {"attempt_id": attempt_id, "attempt_type": mode, "quiz_version": version.version,
             "wildcards_spent": spent, "access_request_id": request_id}
    if spent:
        event.update(gift=wallet["gift"], default=wallet["default"], wildcards_left=wallet["total"])
    return _started(row, questions, wallet["total"]), event


def _started(a, questions: list, wildcards: int, replay: bool = False) -> dict:
    return {
        "attempt_id": str(a.attempt_id), "attempt_type": a.attempt_type, "status": a.status,
        "quiz_version": a.quiz_version, "started_at": _iso(a.started_at), "expires_at": _iso(a.expires_at),
        "wildcards_spent": a.wildcards_spent, "wildcards": wildcards, "replayed": replay,
        "questions": _questions_out(questions),
    }


# ============================================================
# ATTEMPT: get / submit / abandon
# ============================================================

async def _own_attempt(session, user_id: str, attempt_id: str, lock: bool = False):
    try:
        uuid.UUID(attempt_id)
    except ValueError:
        raise QuizError(404, "ATTEMPT_NOT_FOUND", "Quiz attempt not found.")
    row = (await session.execute(text(f"""
        SELECT {ATTEMPT_COLUMNS} FROM quiz_attempts WHERE attempt_id = CAST(:a AS UUID) {'FOR UPDATE' if lock else ''}
    """), {"a": attempt_id})).first()
    if row is None or row.user_id != user_id:          # same answer for "not yours" (no IDOR probing)
        raise QuizError(404, "ATTEMPT_NOT_FOUND", "Quiz attempt not found.")
    return row


async def get_attempt(session, user_id: str, attempt_id: str) -> dict:
    await ensure_schema(session)
    await _expire_stale(session, user_id)
    a = await _own_attempt(session, user_id, attempt_id)
    _, questions, key = await _version(session, a.quiz_version)
    out = _result_out(a, questions, key)
    if a.status == "in_progress":
        out["questions"] = _questions_out(questions)
    return out


def _validate(answers: Any, questions: list) -> dict:
    if not isinstance(answers, dict):
        raise QuizError(400, "VALIDATION_ERROR", "Answers must be an object of question id → option.")
    ids = {q["id"] for q in questions}
    unknown = sorted(set(map(str, answers)) - ids)
    if unknown:
        raise QuizError(400, "VALIDATION_ERROR", f"Unknown question id(s): {', '.join(unknown[:5])}.")
    clean = {}
    for qid, value in answers.items():
        if not isinstance(value, str) or value.upper() not in content.OPTION_KEYS:
            raise QuizError(400, "VALIDATION_ERROR", f"Question {qid}: choose one of A, B, C, D.")
        clean[str(qid)] = value.upper()
    missing = [q["id"] for q in questions if q["id"] not in clean]
    if missing:
        raise QuizError(400, "INCOMPLETE", f"Answer every question before submitting ({len(missing)} left).",
                        {"missing": missing})
    return clean


async def submit(session, user_id: str, attempt_id: str, answers: Any) -> tuple[dict, dict]:
    """Score on the server. A second submit of a completed attempt returns the stored result (duplicate=True)."""
    await ensure_schema(session)
    await _lock_user(session, user_id)
    await _expire_stale(session, user_id)
    a = await _own_attempt(session, user_id, attempt_id, lock=True)
    _, questions, key = await _version(session, a.quiz_version)
    if a.status == "completed":
        return {**_result_out(a, questions, key), "duplicate": True}, {}
    if a.status != "in_progress":
        raise QuizError(409, "ATTEMPT_CLOSED",
                        "This attempt has expired (time limit passed)." if a.status == "expired" else "This attempt was abandoned.",
                        {"status": a.status})
    clean = _validate(answers, questions)
    results = {qid: clean[qid] == key[qid]["answer"] for qid in clean}
    score, total = sum(results.values()), len(questions)
    row = (await session.execute(text(f"""
        UPDATE quiz_attempts
        SET status = 'completed', ended_at = now(), answers = CAST(:ans AS JSONB), results = CAST(:res AS JSONB),
            score = CAST(:s AS INT), total = CAST(:t AS INT), percent = round(100.0 * CAST(:s AS INT) / CAST(:t AS INT), 2),
            duration_s = GREATEST(0, EXTRACT(EPOCH FROM now() - started_at))::int
        WHERE attempt_id = CAST(:a AS UUID) AND status = 'in_progress'
        RETURNING {ATTEMPT_COLUMNS}
    """), {"ans": json.dumps(clean), "res": json.dumps(results), "s": score, "t": total, "a": attempt_id})).first()
    out = {**_result_out(row, questions, key), "duplicate": False}
    event = {"attempt_id": attempt_id, "attempt_type": row.attempt_type, "quiz_version": row.quiz_version,
             "score": score, "total": total, "percent": out["percent"], "duration_s": row.duration_s}
    return out, event


async def abandon(session, user_id: str, attempt_id: str) -> tuple[dict, dict]:
    await ensure_schema(session)
    await _lock_user(session, user_id)
    await _expire_stale(session, user_id)
    a = await _own_attempt(session, user_id, attempt_id, lock=True)
    if a.status != "in_progress":
        return _result_out(a), {}
    row = (await session.execute(text(f"""
        UPDATE quiz_attempts SET status = 'abandoned', ended_at = now(),
               duration_s = GREATEST(0, EXTRACT(EPOCH FROM now() - started_at))::int
        WHERE attempt_id = CAST(:a AS UUID) RETURNING {ATTEMPT_COLUMNS}
    """), {"a": attempt_id})).first()
    return _result_out(row), {"attempt_id": attempt_id, "attempt_type": row.attempt_type}


# ============================================================
# HISTORY / DASHBOARD
# ============================================================

def summarize(rows: list) -> dict:
    """
    Formulas (completed attempts only; abandoned/expired never count as results):
      best/average/latest percent = over completed attempts; average score = mean of score/total
      completion_rate = completed / (completed + abandoned + expired)     (in-progress excluded)
      trend = mean % of the last 3 completed vs the 3 before: >= +5 points improving, <= -5 declining, else steady
    """
    done = [r for r in rows if r["status"] == "completed"]           # rows newest first
    ended = [r for r in rows if r["status"] in ("completed", "abandoned", "expired")]
    pct = [r["percent"] for r in done]
    trend = None
    if len(pct) >= 4:
        recent, before = pct[:3], pct[3:6]
        diff = sum(recent) / len(recent) - sum(before) / len(before)
        trend = "improving" if diff >= 5 else "declining" if diff <= -5 else "steady"
    best = max(done, key=lambda r: (r["percent"], r["ended_at"] or "")) if done else None
    return {
        "total_attempts": len(rows),
        "completed_attempts": len(done),
        "incomplete_attempts": len(ended) - len(done),
        "completion_rate": round(100 * len(done) / len(ended), 1) if ended else None,
        "latest": ({"score": done[0]["score"], "total": done[0]["total"], "percent": done[0]["percent"],
                    "ended_at": done[0]["ended_at"]} if done else None),
        "best": ({"score": best["score"], "total": best["total"], "percent": best["percent"]} if best else None),
        "average_percent": round(sum(pct) / len(pct), 2) if pct else None,
        "average_score": round(sum(r["score"] for r in done) / len(done), 2) if done else None,
        "trend": trend,
        "forced_attempts": sum(1 for r in rows if r["attempt_type"] == "forced"),
        "wildcards_spent": sum(r["wildcards_spent"] for r in rows),
        "last_completed_at": done[0]["ended_at"] if done else None,
        "ever_completed": bool(done),
    }


async def history(session, user_id: str, limit: int = 50) -> dict:
    await ensure_schema(session)
    await _expire_stale(session, user_id)
    rows = (await session.execute(text(f"""
        SELECT {ATTEMPT_COLUMNS} FROM quiz_attempts WHERE user_id = :u ORDER BY started_at DESC LIMIT CAST(:n AS INT)
    """), {"u": user_id, "n": limit})).all()
    items = [_result_out(r) for r in rows]
    return {"summary": summarize(items), "attempts": items}


# ============================================================
# ACCESS REQUESTS (user side)
# ============================================================

async def create_request(session, user_id: str, username: str, reason: Optional[str]) -> tuple[dict, dict]:
    await ensure_schema(session)
    await _lock_user(session, user_id)
    await _expire_stale(session, user_id)
    open_req = (await session.execute(text("""
        SELECT status FROM quiz_access_requests WHERE user_id = :u AND status IN ('pending', 'approved') LIMIT 1
    """), {"u": user_id})).first()
    if open_req is not None:
        raise QuizError(409, "REQUEST_EXISTS",
                        "You already have a request waiting for an admin." if open_req.status == "pending"
                        else "You already have an approved attempt. Use it first.")
    row = (await session.execute(text(f"""
        INSERT INTO quiz_access_requests (user_id, username, quiz_id, reason)
        VALUES (:u, CAST(:name AS TEXT), :q, CAST(:r AS TEXT)) RETURNING {REQUEST_COLUMNS}
    """), {"u": user_id, "name": username, "q": QUIZ_ID, "r": (reason or "").strip()[:500] or None})).first()
    return _request_out(row), {"request_id": str(row.request_id), "reason": row.reason}


async def list_requests(session, user_id: str) -> list:
    await ensure_schema(session)
    await _expire_stale(session, user_id)
    rows = (await session.execute(text(f"""
        SELECT {REQUEST_COLUMNS} FROM quiz_access_requests WHERE user_id = :u ORDER BY created_at DESC LIMIT 50
    """), {"u": user_id})).all()
    return [_request_out(r) for r in rows]
