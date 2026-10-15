"""
DNA quiz backend tests on a REAL PostgreSQL server (no mocks of the database).

Runs the real code of the repository:
  services/gateway/app/routers/quiz.py, app/quiz_service.py, app/routers/wildcards.py, app/quiz_content.py
  apps/admin/services/quiz_admin_service.py
  services/ai/migrations/010_quiz.sql
against PostgreSQL through pgx.py (psql + PREPARE: parameter types are inferred and checked like asyncpg does).
Only the HTTP layer (FastAPI), Redis and the JWT check are replaced by small stand-ins below.
The HTTP layer (login required, 401s, request validation) is covered by tests/test_quiz.py (pytest).

Needs: psql on PATH and a PostgreSQL 14+ server you can create a throwaway database on (default: a local
socket in /tmp, port 5433, user postgres). The database PGX_DB (default "quizt") is DROPPED and re-created.

    PGX_HOST=127.0.0.1 PGX_PORT=5432 PGPASSWORD=... python services/gateway/tests/quiz_db/run_quiz_db_tests.py
"""

import asyncio
import json
import re
import sys
import threading
import time
import traceback
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
GATEWAY, ADMIN_APP = REPO / "services" / "gateway", REPO / "apps" / "admin"
MIGRATION = REPO / "services" / "ai" / "migrations" / "010_quiz.sql"
sys.path[:0] = [str(HERE), str(GATEWAY), str(ADMIN_APP)]

import pgx  # noqa: E402


def _module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


# ---- stand-ins for the parts that are not under test --------------------------------------------
class _Router:
    def __init__(self, *a, **k): pass
    def _deco(self, *a, **k): return lambda f: f
    get = post = patch = put = delete = _deco


class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


_module("fastapi", APIRouter=_Router, Depends=lambda x=None: None, Query=lambda default=None, *a, **k: default,
        HTTPException=HTTPException, Request=object)
_module("sqlalchemy", text=lambda s: s)
_module("app.db", db=pgx.DB(commit=True))             # app/db.py: commit on success, rollback on error


class _CurrentUser:
    def __init__(self, user_id, username, is_admin):
        self.user_id, self.username, self.is_admin = user_id, username, is_admin


async def _no_auth():
    raise RuntimeError("not used here")
_module("app.deps", CurrentUser=_CurrentUser, get_current_user=_no_auth)


class ApiError(Exception):
    def __init__(self, status_code, code, message, fields=None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.fields = status_code, code, message, fields
_module("app.errors", ApiError=ApiError)

EVENTS = []


async def _push(action, user_id, username, is_admin, details=None):
    if not is_admin:
        EVENTS.append((action, user_id, dict(details or {})))
_module("app.logger_client", push_log_event=_push)
_module("db", db=pgx.DB(commit=False))                # apps/admin/db.py: callers must commit


class _Redis:
    async def rpush(self, key, value): pass


async def _get_redis():
    return _Redis()
_module("redis_client", get_redis=_get_redis)

pgx.reset_db()
pgx.psql("CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, is_admin BOOLEAN DEFAULT FALSE)")

from app import quiz_content as content  # noqa: E402
from app import quiz_service as qs  # noqa: E402
from app.routers import quiz as R  # noqa: E402
from services.quiz_admin_service import QuizAdminService as ADM  # noqa: E402

CurrentUser = _CurrentUser
KEY = "".join(content.ANSWER_KEY[str(i)]["answer"] for i in range(1, 21))
ADMIN = type("Admin", (), {"user_id": "admin-1", "username": "teacher", "is_admin": True})()
_users = iter(range(1, 10_000))


def user(name=None) -> CurrentUser:
    n = next(_users)
    uid = str(uuid.uuid4())
    name = name or f"learner{n}"
    pgx.psql(f"INSERT INTO users (user_id, username) VALUES ('{uid}', '{name}')")
    return CurrentUser(uid, name, False)


def key() -> str:
    return "k-" + uuid.uuid4().hex[:16]


def run(coro):
    return asyncio.run(coro)


async def start(u, mode="normal", k=None):
    return await R.start_attempt(R.StartRequest(mode=mode, idempotency_key=k or key()), current_user=u)


async def submit(u, attempt_id, answers):
    return await R.submit_attempt(attempt_id, R.SubmitRequest(answers=answers), current_user=u)


def answers(pattern: str):
    return {str(i + 1): pattern[i] for i in range(20)}


ALL_RIGHT = answers(KEY)
ALL_B = answers("B" * 20)          # 13 of 20 right with this key


def right(n: int) -> str:
    """Answers with exactly the first n correct."""
    return KEY[:n] + "".join("A" if c != "A" else "B" for c in KEY[n:])


async def expect_error(coro, code, status=None):
    try:
        await coro
    except ApiError as e:
        assert e.code == code, f"expected {code}, got {e.code}: {e.message}"
        if status:
            assert e.status_code == status, f"expected HTTP {status}, got {e.status_code}"
        return e
    raise AssertionError(f"expected {code}, but it succeeded")


async def expect_http(coro, status):
    try:
        await coro
    except HTTPException as e:
        assert e.status_code == status, f"expected HTTP {status}, got {e.status_code} {e.detail}"
        return e
    raise AssertionError(f"expected HTTP {status}, but it succeeded")


def wallet(u):
    out = pgx.psql(f"SELECT gift_cards + default_cards FROM wildcard_wallets WHERE user_id = '{u.user_id}'").strip()
    return int(out) if out else None


def set_wallet(u, gift, default):
    pgx.psql(f"UPDATE wildcard_wallets SET gift_cards = {gift}, default_cards = {default}, last_gift_at = now() WHERE user_id = '{u.user_id}'")


def q1(sql):
    return pgx.psql(sql).strip()


def shift_attempts(u, hours):
    """Move the user's attempts back in time (instead of waiting 12 hours)."""
    pgx.psql(f"UPDATE quiz_attempts SET started_at = started_at - interval '{hours} hours', "
             f"expires_at = expires_at - interval '{hours} hours', ended_at = ended_at - interval '{hours} hours' "
             f"WHERE user_id = '{u.user_id}'")


def threads(fns):
    """Run the callables at the same moment, each in its own thread / event loop / DB connection."""
    results = [None] * len(fns)
    barrier = threading.Barrier(len(fns))

    def go(i, fn):
        barrier.wait()
        try:
            results[i] = ("ok", asyncio.run(fn()))
        except Exception as e:  # noqa: BLE001
            results[i] = ("err", e)

    ts = [threading.Thread(target=go, args=(i, f)) for i, f in enumerate(fns)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    return results


async def cooldown_user():
    """A learner who just finished one attempt (now in the 12 h cooldown)."""
    u = user()
    await R.quiz_status(current_user=u)
    a = await start(u)
    await submit(u, a["attempt_id"], ALL_B)
    return u


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# ------------------------------------------------------------------ migration / schema
@test
async def migration_runs_on_fresh_db_and_again_and_runtime_setup_is_idempotent():
    pgx.psql(MIGRATION.read_text())          # as Postgres initdb would
    pgx.psql(MIGRATION.read_text())          # re-running changes nothing
    u = user()
    s = await R.quiz_status(current_user=u)  # runtime ensure_schema on top
    assert s["quiz"]["question_count"] == 20 and s["quiz"]["version"] == 1
    idx = q1("SELECT string_agg(indexname, ',' ORDER BY indexname) FROM pg_indexes WHERE tablename IN ('quiz_attempts','quiz_access_requests','wildcard_ledger')")
    for name in ("uq_quiz_attempt_active", "uq_quiz_attempt_request", "uq_quiz_request_pending", "uq_quiz_request_approved",
                 "idx_quiz_attempts_user", "idx_quiz_attempts_results", "wildcard_ledger_idempotency_key_key"):
        assert name in idx, name
    assert q1("SELECT count(*) FROM quiz_versions") == "1"


@test
async def answer_key_matches_the_pdf_and_is_stored_server_side_only():
    assert KEY == "BABBCBBBCBBBCDCBABBB"
    assert len(content.QUESTIONS) == 20
    assert [q["level"] for q in content.QUESTIONS].count("easy") == 6
    stored = json.loads(q1("SELECT answer_key FROM quiz_versions WHERE quiz_id = 'dna' AND version = 1"))
    assert {k: v["answer"] for k, v in stored.items()} == {str(i + 1): KEY[i] for i in range(20)}


# ------------------------------------------------------------------ quiz functionality
@test
async def start_never_sends_the_answer_key():
    u = user()
    a = await start(u)
    assert a["status"] == "in_progress" and len(a["questions"]) == 20
    for q in a["questions"]:
        assert set(q) == {"id", "level", "text", "options"}, q.keys()
    blob = json.dumps(a)
    assert "explanation" not in blob and "answer" not in blob and "correct" not in blob
    again = await R.get_attempt(a["attempt_id"], current_user=u)   # resume view: questions, still no key
    assert "review" not in again and "answer" not in json.dumps(again["questions"])


@test
async def all_correct_scores_20_of_20():
    u = user()
    a = await start(u)
    r = await submit(u, a["attempt_id"], ALL_RIGHT)
    assert (r["score"], r["total"], r["correct"], r["incorrect"], r["percent"], r["status"]) == (20, 20, 20, 0, 100.0, "completed")
    assert r["duplicate"] is False and r["duration_s"] is not None and r["ended_at"]
    assert all(x["correct"] for x in r["review"])


@test
async def mixed_answers_are_scored_on_the_server():
    u = user()
    a = await start(u)
    r = await submit(u, a["attempt_id"], ALL_B)
    assert (r["score"], r["incorrect"], r["percent"]) == (13, 7, 65.0)
    wrong = [x for x in r["review"] if not x["correct"]]
    assert {x["id"] for x in wrong} == {"2", "5", "9", "13", "14", "15", "17"}
    assert all(x["correct_answer"] != "B" and x["your_answer"] == "B" and x["explanation"] for x in wrong)
    row = q1(f"SELECT status || '|' || score || '|' || total || '|' || percent FROM quiz_attempts WHERE attempt_id = '{a['attempt_id']}'")
    assert row == "completed|13|20|65.00", row


@test
async def lowercase_options_are_accepted():
    u = user()
    a = await start(u)
    r = await submit(u, a["attempt_id"], {k: v.lower() for k, v in ALL_RIGHT.items()})
    assert r["score"] == 20


@test
async def malformed_missing_and_invalid_submissions_are_rejected_and_change_nothing():
    u = user()
    a = await start(u)
    aid = a["attempt_id"]
    await expect_error(submit(u, aid, ["B"] * 20), "VALIDATION_ERROR", 400)
    await expect_error(submit(u, aid, None), "VALIDATION_ERROR", 400)
    await expect_error(submit(u, aid, {**ALL_RIGHT, "21": "A"}), "VALIDATION_ERROR", 400)
    await expect_error(submit(u, aid, {**ALL_RIGHT, "3": "E"}), "VALIDATION_ERROR", 400)
    await expect_error(submit(u, aid, {**ALL_RIGHT, "3": 2}), "VALIDATION_ERROR", 400)
    partial = dict(list(ALL_RIGHT.items())[:15])
    e = await expect_error(submit(u, aid, partial), "INCOMPLETE", 400)
    assert e.fields["missing"] == "16,17,18,19,20"
    assert q1(f"SELECT status FROM quiz_attempts WHERE attempt_id = '{aid}'") == "in_progress"
    r = await submit(u, aid, ALL_RIGHT)              # still submittable afterwards
    assert r["score"] == 20
    try:
        R.StartRequest(mode="hack", idempotency_key=key())
        raise AssertionError("bad mode accepted")
    except ValueError:
        pass
    for bad in ("short", "x" * 81, "has space!!"):
        try:
            R.StartRequest(mode="normal", idempotency_key=bad)
            raise AssertionError(f"bad key accepted: {bad}")
        except ValueError:
            pass


@test
async def duplicate_submit_returns_the_stored_result_once():
    u = user()
    a = await start(u)
    first = await submit(u, a["attempt_id"], ALL_B)
    EVENTS.clear()
    again = await submit(u, a["attempt_id"], ALL_RIGHT)   # replay with different answers: ignored
    assert again["duplicate"] is True and again["score"] == first["score"] == 13
    assert q1(f"SELECT count(*) FROM quiz_attempts WHERE user_id = '{u.user_id}' AND status = 'completed'") == "1"
    assert not [e for e in EVENTS if e[0] == "quiz_completed"], "a duplicate must not log a second completion"


@test
async def concurrent_submits_create_one_completed_result():
    u = user()
    a = await start(u)
    res = threads([lambda: submit(u, a["attempt_id"], ALL_B) for _ in range(6)])
    assert all(r[0] == "ok" for r in res), res
    dup = sorted(r[1]["duplicate"] for r in res)
    assert dup == [False] + [True] * 5, dup
    assert {r[1]["score"] for r in res} == {13}
    assert q1(f"SELECT count(*) FROM quiz_attempts WHERE user_id = '{u.user_id}' AND status = 'completed'") == "1"


@test
async def other_users_cannot_read_submit_or_abandon_an_attempt():
    owner, other = user(), user()
    a = await start(owner)
    aid = a["attempt_id"]
    await expect_error(R.get_attempt(aid, current_user=other), "ATTEMPT_NOT_FOUND", 404)
    await expect_error(submit(other, aid, ALL_RIGHT), "ATTEMPT_NOT_FOUND", 404)
    await expect_error(R.abandon_attempt(aid, current_user=other), "ATTEMPT_NOT_FOUND", 404)
    await expect_error(R.get_attempt("not-a-uuid", current_user=owner), "ATTEMPT_NOT_FOUND", 404)
    await expect_error(R.get_attempt(str(uuid.uuid4()), current_user=owner), "ATTEMPT_NOT_FOUND", 404)
    assert q1(f"SELECT status FROM quiz_attempts WHERE attempt_id = '{aid}'") == "in_progress"
    h = await R.quiz_history(current_user=other)
    assert h["attempts"] == []


@test
async def results_and_events_never_log_the_submitted_answers():
    u = user()
    EVENTS.clear()
    a = await start(u)
    await submit(u, a["attempt_id"], ALL_B)
    done = [d for act, uid, d in EVENTS if act == "quiz_completed"]
    assert done and done[0]["score"] == 13
    assert "answers" not in json.dumps(EVENTS) and "review" not in json.dumps(EVENTS)


# ------------------------------------------------------------------ cooldown / idempotent start
@test
async def attempt_allowed_when_eligible_and_blocked_during_the_12h_cooldown():
    u = user()
    s = await R.quiz_status(current_user=u)
    assert s["eligible"] and s["next_eligible_at"] is None and s["cooldown_remaining_s"] == 0
    a = await start(u)
    await expect_error(start(u), "ATTEMPT_IN_PROGRESS", 409)
    await submit(u, a["attempt_id"], ALL_B)
    e = await expect_error(start(u), "COOLDOWN", 429)
    assert 12 * 3600 - 60 < int(e.fields["cooldown_remaining_s"]) <= 12 * 3600
    s = await R.quiz_status(current_user=u)
    assert not s["eligible"] and s["can_force"] and s["next_eligible_at"]
    started = datetime.fromisoformat(a["started_at"])
    assert datetime.fromisoformat(s["next_eligible_at"]) == started + timedelta(hours=12)   # server time, from the start
    shift_attempts(u, 11.9)
    await expect_error(start(u), "COOLDOWN", 429)
    shift_attempts(u, 0.11)
    s = await R.quiz_status(current_user=u)
    assert s["eligible"], s
    b = await start(u)
    assert b["attempt_type"] == "normal"


@test
async def start_retry_with_the_same_key_returns_the_same_attempt():
    u = user()
    k = key()
    a = await start(u, k=k)
    b = await start(u, k=k)
    assert b["attempt_id"] == a["attempt_id"] and b["replayed"] is True
    assert q1(f"SELECT count(*) FROM quiz_attempts WHERE user_id = '{u.user_id}'") == "1"
    await submit(u, a["attempt_id"], ALL_B)
    await expect_error(start(u, k=k), "ATTEMPT_CLOSED", 409)


# ------------------------------------------------------------------ force attempt / wildcards
@test
async def forced_attempt_costs_exactly_3_wildcards_with_a_ledger_entry():
    u = await cooldown_user()
    set_wallet(u, 2, 3)
    k = key()
    a = await start(u, "forced", k)
    assert a["attempt_type"] == "forced" and a["wildcards_spent"] == 3 and a["wildcards"] == 2
    assert wallet(u) == 2
    led = q1(f"SELECT delta || '|' || reason || '|' || ref || '|' || idempotency_key || '|' || gift_after || '|' || default_after "
             f"FROM wildcard_ledger WHERE user_id = '{u.user_id}' AND reason = 'quiz_force'")
    assert led == f"-3|quiz_force|{a['attempt_id']}|quiz_force:{u.user_id}:{k}|0|2", led


@test
async def forced_attempt_with_exactly_3_wildcards_leaves_0():
    u = await cooldown_user()
    set_wallet(u, 0, 3)
    a = await start(u, "forced")
    assert a["wildcards"] == 0 and wallet(u) == 0


@test
async def forced_attempt_is_rejected_without_enough_wildcards_and_takes_nothing():
    u = await cooldown_user()
    set_wallet(u, 1, 1)
    e = await expect_error(start(u, "forced"), "NOT_ENOUGH_WILDCARDS", 402)
    assert e.fields == {"wildcards": "2", "force_cost": "3"}
    assert wallet(u) == 2
    assert q1(f"SELECT count(*) FROM wildcard_ledger WHERE user_id = '{u.user_id}' AND reason = 'quiz_force'") == "0"
    assert q1(f"SELECT count(*) FROM quiz_attempts WHERE user_id = '{u.user_id}'") == "1"
    s = await R.quiz_status(current_user=u)
    assert s["can_force"] is False


@test
async def forced_attempt_is_refused_when_no_cooldown_and_while_another_attempt_runs():
    u = user()
    await R.quiz_status(current_user=u)
    before = wallet(u)
    await expect_error(start(u, "forced"), "FORCE_NOT_NEEDED", 409)
    assert wallet(u) == before
    u2 = await cooldown_user()
    set_wallet(u2, 6, 6)
    a = await start(u2, "forced")
    await expect_error(start(u2, "forced"), "ATTEMPT_IN_PROGRESS", 409)
    assert wallet(u2) == 9 and a["wildcards_spent"] == 3


@test
async def forced_retry_with_the_same_key_never_charges_twice():
    u = await cooldown_user()
    set_wallet(u, 4, 4)
    k = key()
    a = await start(u, "forced", k)
    b = await start(u, "forced", k)
    assert a["attempt_id"] == b["attempt_id"] and b["replayed"]
    assert wallet(u) == 5
    assert q1(f"SELECT count(*) FROM wildcard_ledger WHERE user_id = '{u.user_id}' AND reason = 'quiz_force'") == "1"


@test
async def concurrent_forced_attempts_deduct_once():
    u = await cooldown_user()
    set_wallet(u, 3, 4)
    res = threads([lambda: start(u, "forced") for _ in range(6)])        # 6 taps, 6 different keys, same moment
    ok = [r for r in res if r[0] == "ok"]
    errs = [r[1].code for r in res if r[0] == "err"]
    assert len(ok) == 1 and errs == ["ATTEMPT_IN_PROGRESS"] * 5, (ok, errs)
    assert wallet(u) == 4
    assert q1(f"SELECT count(*) FROM wildcard_ledger WHERE user_id = '{u.user_id}' AND reason = 'quiz_force'") == "1"
    u2 = await cooldown_user()
    set_wallet(u2, 3, 4)
    k = key()
    res = threads([lambda: start(u2, "forced", k) for _ in range(6)])    # 6 retries of ONE tap
    assert all(r[0] == "ok" for r in res), res
    assert len({r[1]["attempt_id"] for r in res}) == 1
    assert wallet(u2) == 4
    assert q1(f"SELECT count(*) FROM quiz_attempts WHERE user_id = '{u2.user_id}' AND attempt_type = 'forced'") == "1"


@test
async def ledger_idempotency_key_is_enforced_by_the_database():
    try:
        pgx.psql("INSERT INTO wildcard_ledger (user_id, delta, reason, idempotency_key) VALUES ('x', -3, 'quiz_force', 'dup-key');"
                 "INSERT INTO wildcard_ledger (user_id, delta, reason, idempotency_key) VALUES ('x', -3, 'quiz_force', 'dup-key')")
        raise AssertionError("duplicate ledger key accepted")
    except pgx.SQLError as e:
        assert "duplicate key" in str(e)


# ------------------------------------------------------------------ abandoned / expired policy
@test
async def abandoned_attempt_counts_for_cooldown_has_no_score_and_keeps_forced_cost():
    u = await cooldown_user()
    set_wallet(u, 0, 5)
    a = await start(u, "forced")
    r = await R.abandon_attempt(a["attempt_id"], current_user=u)
    assert r["status"] == "abandoned" and r["score"] is None
    assert wallet(u) == 2                                         # no refund: the questions were seen
    await expect_error(submit(u, a["attempt_id"], ALL_RIGHT), "ATTEMPT_CLOSED", 409)
    await expect_error(start(u), "COOLDOWN", 429)                 # the abandoned start still counts
    again = await R.abandon_attempt(a["attempt_id"], current_user=u)
    assert again["status"] == "abandoned"
    h = await R.quiz_history(current_user=u)
    assert h["summary"]["completed_attempts"] == 1 and h["summary"]["incomplete_attempts"] == 1


@test
async def unsubmitted_attempt_expires_after_the_time_limit():
    u = user()
    a = await start(u)
    pgx.psql(f"UPDATE quiz_attempts SET expires_at = now() - interval '1 second' WHERE attempt_id = '{a['attempt_id']}'")
    s = await R.quiz_status(current_user=u)
    assert s["active_attempt"] is None and not s["eligible"]      # expired, and it still used the 12 h slot
    assert q1(f"SELECT status FROM quiz_attempts WHERE attempt_id = '{a['attempt_id']}'") == "expired"
    e = await expect_error(submit(u, a["attempt_id"], ALL_RIGHT), "ATTEMPT_CLOSED", 409)
    assert e.fields["status"] == "expired"


# ------------------------------------------------------------------ access requests + approvals
async def request(u, reason="exam tomorrow"):
    return await R.create_access_request(R.AccessRequestBody(reason=reason), current_user=u)


@test
async def one_pending_request_per_user_and_duplicates_are_rejected():
    u = await cooldown_user()
    r = await request(u)
    assert r["status"] == "pending" and r["reason"] == "exam tomorrow" and r["created_at"]
    await expect_error(request(u, "again"), "REQUEST_EXISTS", 409)
    s = await R.quiz_status(current_user=u)
    assert s["pending_request"]["request_id"] == r["request_id"] and s["can_request"] is False
    mine = await R.my_access_requests(current_user=u)
    assert [x["status"] for x in mine] == ["pending"]
    other = user()
    assert await R.my_access_requests(current_user=other) == []


@test
async def concurrent_requests_create_one_pending_request():
    u = await cooldown_user()
    res = threads([lambda: request(u) for _ in range(6)])
    ok = [r for r in res if r[0] == "ok"]
    assert len(ok) == 1 and all(r[1].code == "REQUEST_EXISTS" for r in res if r[0] == "err"), res
    assert q1(f"SELECT count(*) FROM quiz_access_requests WHERE user_id = '{u.user_id}'") == "1"


@test
async def database_allows_only_one_pending_and_one_approved_request():
    uid = str(uuid.uuid4())
    for status_ in ("pending", "approved"):
        extra = ", window_start, window_end" if status_ == "approved" else ""
        vals = ", now(), now() + interval '1 hour'" if status_ == "approved" else ""
        sql = f"INSERT INTO quiz_access_requests (user_id, status{extra}) VALUES ('{uid}', '{status_}'{vals})"
        pgx.psql(sql)
        try:
            pgx.psql(sql)
            raise AssertionError(f"second {status_} request accepted")
        except pgx.SQLError as e:
            assert "duplicate key" in str(e)


@test
async def approval_authorizes_exactly_one_start_then_is_used():
    u = await cooldown_user()
    r = await request(u)
    d = await ADM.decide(r["request_id"], ADMIN, True, "ok, good luck", None, None, 6)
    assert d["status"] == "approved" and d["decided_by"] == "teacher" and d["cooldown_hours"] == 6
    s = await R.quiz_status(current_user=u)                     # a NEW session: the decision was committed
    assert s["authorization"]["usable_now"] is True and s["can_request"] is False
    audit = q1(f"SELECT admin_username || '|' || action || '|' || target_user_id FROM admin_audit_log WHERE target_id = '{r['request_id']}'")
    assert audit == f"teacher|quiz_access_approved|{u.user_id}", audit
    await expect_error(start(u), "COOLDOWN", 429)               # a normal start does not use the approval
    a = await start(u, "authorized")
    assert a["attempt_type"] == "authorized"
    row = q1(f"SELECT status || '|' || used_attempt_id FROM quiz_access_requests WHERE request_id = '{r['request_id']}'")
    assert row == f"used|{a['attempt_id']}", row
    assert q1(f"SELECT cooldown_hours || '|' || access_request_id FROM quiz_attempts WHERE attempt_id = '{a['attempt_id']}'") == f"6|{r['request_id']}"
    await submit(u, a["attempt_id"], ALL_RIGHT)
    await expect_error(start(u, "authorized"), "NOT_AUTHORIZED", 403)  # never reusable
    s = await R.quiz_status(current_user=u)
    assert s["authorization"] is None and s["can_request"] is True
    assert 6 * 3600 - 120 < s["cooldown_remaining_s"] <= 6 * 3600  # the approval's own cooldown


@test
async def concurrent_authorized_starts_use_the_approval_once():
    u = await cooldown_user()
    r = await request(u)
    await ADM.decide(r["request_id"], ADMIN, True, None)
    res = threads([lambda: start(u, "authorized") for _ in range(6)])
    ok = [x for x in res if x[0] == "ok"]
    assert len(ok) == 1, res
    assert {x[1].code for x in res if x[0] == "err"} <= {"ATTEMPT_IN_PROGRESS", "NOT_AUTHORIZED"}
    assert q1(f"SELECT count(*) FROM quiz_attempts WHERE access_request_id = '{r['request_id']}'") == "1"


@test
async def scheduled_approval_cannot_start_before_its_window():
    u = await cooldown_user()
    r = await request(u)
    start_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    end_at = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    await ADM.decide(r["request_id"], ADMIN, True, None, start_at, end_at, 12)
    s = await R.quiz_status(current_user=u)
    assert s["authorization"]["usable_now"] is False
    await expect_error(start(u, "authorized"), "NOT_YET", 403)
    assert q1(f"SELECT status FROM quiz_access_requests WHERE request_id = '{r['request_id']}'") == "approved"


@test
async def expired_window_cannot_start_and_shows_expired():
    u = await cooldown_user()
    r = await request(u)
    await ADM.decide(r["request_id"], ADMIN, True, None)
    pgx.psql(f"UPDATE quiz_access_requests SET window_start = now() - interval '2 hours', window_end = now() - interval '1 second' "
             f"WHERE request_id = '{r['request_id']}'")
    await expect_error(start(u, "authorized"), "NOT_AUTHORIZED", 403)
    mine = await R.my_access_requests(current_user=u)
    assert mine[0]["status"] == "expired"
    assert (await request(u))["status"] == "pending"            # a new request is allowed afterwards


@test
async def approval_is_kept_when_no_cooldown_is_running():
    u = await cooldown_user()
    r = await request(u)
    await ADM.decide(r["request_id"], ADMIN, True, None, None, (datetime.now(timezone.utc) + timedelta(days=2)).isoformat())
    shift_attempts(u, 13)                                       # cooldown over: a normal start is free
    await expect_error(start(u, "authorized"), "AUTH_NOT_NEEDED", 409)
    assert q1(f"SELECT status FROM quiz_access_requests WHERE request_id = '{r['request_id']}'") == "approved"


@test
async def an_approved_request_blocks_new_requests_until_used_or_expired():
    u = await cooldown_user()
    r = await request(u)
    await ADM.decide(r["request_id"], ADMIN, True, None)
    e = await expect_error(request(u), "REQUEST_EXISTS", 409)
    assert "approved" in e.message


@test
async def reject_needs_a_reason_and_only_pending_requests_can_be_decided():
    u = await cooldown_user()
    r = await request(u)
    await expect_http(ADM.decide(r["request_id"], ADMIN, False, ""), 400)
    d = await ADM.decide(r["request_id"], ADMIN, False, "Not this week")
    assert d["status"] == "rejected" and d["decision_reason"] == "Not this week" and d["decided_at"]
    assert q1(f"SELECT status FROM quiz_access_requests WHERE request_id = '{r['request_id']}'") == "rejected"
    await expect_http(ADM.decide(r["request_id"], ADMIN, True, None), 409)
    await expect_error(start(u, "authorized"), "NOT_AUTHORIZED", 403)
    assert (await request(u))["status"] == "pending"            # a new request is fine after a decision
    await expect_http(ADM.decide("nope", ADMIN, True, None), 404)
    await expect_http(ADM.decide(str(uuid.uuid4()), ADMIN, True, None), 404)


@test
async def approval_window_and_cooldown_are_validated():
    u = await cooldown_user()
    r = await request(u)
    now = datetime.now(timezone.utc)
    rid = r["request_id"]
    await expect_http(ADM.decide(rid, ADMIN, True, None, now.isoformat(), (now - timedelta(hours=1)).isoformat()), 400)
    await expect_http(ADM.decide(rid, ADMIN, True, None, (now - timedelta(hours=3)).isoformat(), (now - timedelta(hours=1)).isoformat()), 400)
    await expect_http(ADM.decide(rid, ADMIN, True, None, now.isoformat(), (now + timedelta(days=8)).isoformat()), 400)
    await expect_http(ADM.decide(rid, ADMIN, True, None, None, None, 500), 400)
    await expect_http(ADM.decide(rid, ADMIN, True, None, "yesterday"), 400)
    assert q1(f"SELECT status FROM quiz_access_requests WHERE request_id = '{rid}'") == "pending"


@test
async def concurrent_admin_decisions_decide_once():
    u = await cooldown_user()
    r = await request(u)
    res = threads([lambda: ADM.decide(r["request_id"], ADMIN, True, None)] * 3 + [lambda: ADM.decide(r["request_id"], ADMIN, False, "no way")] * 3)
    ok = [x for x in res if x[0] == "ok"]
    assert len(ok) == 1 and all(isinstance(x[1], HTTPException) and x[1].status_code == 409 for x in res if x[0] == "err"), res
    assert q1(f"SELECT count(*) FROM admin_audit_log WHERE target_id = '{r['request_id']}'") == "1"


# ------------------------------------------------------------------ dashboard / summaries
@test
async def history_summary_excludes_incomplete_attempts():
    u = user()
    a = await start(u)
    await submit(u, a["attempt_id"], answers(right(12)))    # 12 right -> 60 %
    shift_attempts(u, 13)
    b = await start(u)
    await R.abandon_attempt(b["attempt_id"], current_user=u)
    shift_attempts(u, 13)
    c = await start(u)
    await submit(u, c["attempt_id"], answers(right(16)))    # 16 right -> 80 %
    h = await R.quiz_history(current_user=u)
    s = h["summary"]
    assert (s["total_attempts"], s["completed_attempts"], s["incomplete_attempts"]) == (3, 2, 1), s
    assert s["latest"]["score"] == 16 and s["best"]["percent"] == 80.0 and s["average_percent"] == 70.0
    assert s["average_score"] == 14.0 and s["completion_rate"] == 66.7 and s["ever_completed"]
    assert [x["status"] for x in h["attempts"]] == ["completed", "abandoned", "completed"]   # newest first, with dates
    assert all(x["started_at"] for x in h["attempts"])


@test
async def summary_formulas_trend_best_and_rates():
    def row(p, status="completed", t="normal", spent=0, when="2026-10-01"):
        return {"status": status, "percent": p, "score": None if p is None else int(p / 5), "total": 20,
                "attempt_type": t, "wildcards_spent": spent, "ended_at": when}
    up = [row(90), row(85), row(80), row(60), row(65), row(70)]           # newest first
    s = qs.summarize(up)
    assert s["trend"] == "improving" and s["best"]["percent"] == 90 and s["average_percent"] == 75.0
    assert qs.summarize(list(reversed(up)))["trend"] == "declining"
    assert qs.summarize([row(70), row(72), row(68), row(70)])["trend"] == "steady"
    assert qs.summarize([row(70), row(80), row(90)])["trend"] is None      # needs 4+ results
    mix = [row(50, t="forced", spent=3), row(None, "abandoned", "forced", 3), row(None, "expired"), row(None, "in_progress")]
    s = qs.summarize(mix)
    assert (s["completed_attempts"], s["incomplete_attempts"], s["completion_rate"]) == (1, 2, 33.3)
    assert (s["forced_attempts"], s["wildcards_spent"], s["average_percent"]) == (2, 6, 50.0)
    empty = qs.summarize([])
    assert empty["latest"] is None and empty["completion_rate"] is None and empty["average_percent"] is None


@test
async def status_shows_request_state_and_wildcards_for_the_dashboard():
    u = await cooldown_user()
    set_wallet(u, 1, 1)
    s = await R.quiz_status(current_user=u)
    assert s["wildcards"] == 2 and s["force_cost"] == 3 and s["can_force"] is False
    r = await request(u)
    s = await R.quiz_status(current_user=u)
    assert s["pending_request"]["request_id"] == r["request_id"]
    await ADM.decide(r["request_id"], ADMIN, False, "not now")
    s = await R.quiz_status(current_user=u)
    assert s["pending_request"] is None and s["requests"][0]["status"] == "rejected" and s["requests"][0]["decided_by"] == "teacher"


# ------------------------------------------------------------------ admin analytics
@test
async def admin_quiz_log_filters_pagination_and_result_display():
    pgx.psql("TRUNCATE quiz_attempts, quiz_access_requests CASCADE")
    ann, bob = user("ann_log"), user("bob_log")
    for pattern in ("B" * 20, KEY):                       # ann: 65 %, then 100 % (forced)
        a = await start(ann)
        await submit(ann, a["attempt_id"], answers(pattern))
        shift_attempts(ann, 13)
    pgx.psql(f"UPDATE quiz_attempts SET attempt_type = 'forced', wildcards_spent = 3 WHERE user_id = '{ann.user_id}' AND score = 20")
    b = await start(bob)
    await R.abandon_attempt(b["attempt_id"], current_user=bob)
    page = await ADM.list_attempts()
    assert page["total"] == 2 and all(i["status"] == "completed" for i in page["items"])   # results only by default
    top = page["items"][0]                                  # newest first
    assert top["username"] == "ann_log" and (top["score"], top["total"], top["percent"]) == (20, 20, 100.0)
    assert top["attempt_type"] == "forced" and top["wildcards_spent"] == 3
    assert datetime.fromisoformat(top["ended_at"]).tzinfo is not None                       # consistent timezone (ISO, UTC offset)
    assert (await ADM.list_attempts(status="incomplete"))["items"][0]["username"] == "bob_log"
    assert (await ADM.list_attempts(user="bob"))["total"] == 0
    assert (await ADM.list_attempts(user="ann", min_percent=90))["items"][0]["percent"] == 100.0
    assert (await ADM.list_attempts(max_percent=70))["total"] == 1
    assert (await ADM.list_attempts(attempt_type="forced"))["total"] == 1
    assert (await ADM.list_attempts(status="all"))["total"] == 3
    p1 = await ADM.list_attempts(status="all", page=1, page_size=2)
    p2 = await ADM.list_attempts(status="all", page=2, page_size=2)
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1 and p1["total"] == 3
    assert not {i["attempt_id"] for i in p1["items"]} & {i["attempt_id"] for i in p2["items"]}
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert (await ADM.list_attempts(date_from=future))["total"] == 0
    past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert (await ADM.list_attempts(date_from=past, date_to=future))["total"] == 2
    await expect_http(ADM.list_attempts(status="weird"), 400)
    await expect_http(ADM.list_attempts(date_from="not a date"), 400)
    detail = await ADM.attempt_detail(page["items"][1]["attempt_id"])
    assert detail["percent"] == 65.0 and detail["quiz_version"] == 1
    assert len(detail["questions"]) == 20 and sum(q["correct"] for q in detail["questions"]) == 13
    assert "correct_answer" not in json.dumps(detail) and "explanation" not in json.dumps(detail)
    await expect_http(ADM.attempt_detail("x"), 404)


@test
async def admin_user_performance_and_ranking_score_v1():
    pgx.psql("TRUNCATE quiz_attempts, quiz_access_requests CASCADE")
    cy = user("cy_perf")
    for pattern in (right(12), right(16), KEY, "B" * 20):   # 60, 80, 100, 65 (newest last)
        a = await start(cy)
        await submit(cy, a["attempt_id"], answers(pattern))
        shift_attempts(cy, 13)
    c = await start(cy)
    await R.abandon_attempt(c["attempt_id"], current_user=cy)
    page = await ADM.list_users(search="cy_perf")
    assert page["total"] == 1
    u = page["items"][0]
    assert (u["attempts"], u["completed"], u["incomplete"]) == (5, 4, 1)
    assert (u["latest_score"], u["latest_total"], u["best_percent"], u["avg_percent"]) == (13, 20, 100.0, 76.25), u
    assert u["recent_avg_percent"] == round((65 + 100 + 80) / 3, 2)
    assert u["completion_rate"] == 80.0 and u["trend"] == "improving"      # last 3 (81.7) vs the one before (60)
    expected = round(0.5 * 76.25 + 0.3 * 100 + 0.2 * ((65 + 100 + 80) / 3), 2)
    assert u["ranking_score_v1"] == expected, (u["ranking_score_v1"], expected)
    assert u["next_eligible_at"] and u["cooldown_remaining_s"] > 11 * 3600
    d = await ADM.user_detail(cy.user_id)
    assert d["summary"]["user_id"] == cy.user_id and len(d["attempts"]) == 5


@test
async def admin_summary_uses_the_same_inclusion_rules():
    pgx.psql("TRUNCATE quiz_attempts, quiz_access_requests CASCADE")
    d1, d2 = user("dee"), user("eli")
    a = await start(d1)
    await submit(d1, a["attempt_id"], answers(KEY))                  # 100
    b = await start(d2)
    await submit(d2, b["attempt_id"], answers(right(12)))  # 60
    shift_attempts(d2, 13)
    c = await start(d2)
    await R.abandon_attempt(c["attempt_id"], current_user=d2)
    await request(d2)
    s = await ADM.summary()
    assert s["ready"] and s["completed_attempts"] == 2 and s["incomplete_attempts"] == 1 and s["started_attempts"] == 3
    assert s["avg_percent"] == 80.0 and s["median_percent"] == 80.0 and s["completion_rate"] == 66.7
    assert {b_["label"]: b_["count"] for b_ in s["distribution"]} == {"0-49%": 0, "50-69%": 1, "70-89%": 0, "90-100%": 1}
    assert s["requests"]["pending"] == 1 and s["completers"] == 2 and s["participation_percent"] is not None


@test
async def admin_request_list_filters_and_pagination():
    pgx.psql("TRUNCATE quiz_attempts, quiz_access_requests CASCADE")
    f1, f2, f3 = await cooldown_user(), await cooldown_user(), await cooldown_user()
    r1, r2, r3 = await request(f1), await request(f2), await request(f3)
    await ADM.decide(r2["request_id"], ADMIN, False, "nope")
    all_ = await ADM.list_requests()
    assert all_["total"] == 3 and all_["items"][0]["status"] == "pending"           # pending first
    assert (await ADM.list_requests(status="rejected"))["items"][0]["request_id"] == r2["request_id"]
    assert (await ADM.list_requests(user=f3.username))["items"][0]["request_id"] == r3["request_id"]
    p = await ADM.list_requests(page=2, page_size=2)
    assert len(p["items"]) == 1 and p["total"] == 3
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert (await ADM.list_requests(date_from=future))["total"] == 0


# ------------------------------------------------------------------ access control (static: FastAPI wiring)
@test
async def every_admin_quiz_route_requires_an_admin_and_every_app_route_a_login():
    admin_src = (ADMIN_APP / "routers" / "quiz.py").read_text()
    routes = re.findall(r"@router\.(get|post)\(.*?\)\s*\nasync def (\w+)\((.*?)\)\s*(?:->[^:]*)?:", admin_src, re.S)
    assert len(routes) == 8, routes
    for _m, name, params in routes:
        assert "Depends(require_admin)" in params, name
    gw_src = (GATEWAY / "app" / "routers" / "quiz.py").read_text()
    routes = re.findall(r"@router\.(get|post)\(.*?\)\s*\nasync def (\w+)\((.*?)\)\s*(?:->[^:]*)?:", gw_src, re.S)
    assert len(routes) == 8, routes
    for _m, name, params in routes:
        assert "Depends(get_current_user)" in params, name


def main():
    passed, failed = 0, []
    t0 = time.time()
    for fn in TESTS:
        try:
            run(fn())
            passed += 1
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            failed.append(fn.__name__)
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {len(failed)} failed in {time.time() - t0:.1f}s")
    if failed:
        print("failed:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
