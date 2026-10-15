"""
/api/quiz over HTTP: the real FastAPI app, asyncpg and a private PostgreSQL cluster (fixtures in conftest.py).

The business rules in depth (concurrency, Force Attempt ledger, approvals, admin analytics) are covered by
tests/quiz_db/run_quiz_db_tests.py; this file checks the HTTP contract: login required, request validation,
error codes, and that the answer key never reaches the client before submission.
"""

import uuid

import pytest

from app import quiz_content as content
from tests.utils import bearer, error_of, register_ok, sql

KEY = {qid: v["answer"] for qid, v in content.ANSWER_KEY.items()}


def _start(client, auth, mode="normal", key=None):
    return client.post("/api/quiz/attempts", headers=bearer(auth["token"]),
                       json={"mode": mode, "idempotency_key": key or f"k-{uuid.uuid4().hex[:16]}"})


def _submit(client, auth, attempt_id, answers):
    return client.post(f"/api/quiz/attempts/{attempt_id}/submit", headers=bearer(auth["token"]), json={"answers": answers})


@pytest.mark.parametrize("method,path", [
    ("get", "/api/quiz/status"),
    ("post", "/api/quiz/attempts"),
    ("get", f"/api/quiz/attempts/{uuid.uuid4()}"),
    ("post", f"/api/quiz/attempts/{uuid.uuid4()}/submit"),
    ("post", f"/api/quiz/attempts/{uuid.uuid4()}/abandon"),
    ("get", "/api/quiz/history"),
    ("post", "/api/quiz/access-requests"),
    ("get", "/api/quiz/access-requests"),
])
def test_every_quiz_route_needs_a_login(client, method, path):
    response = getattr(client, method)(path, json={})
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_MISSING"


def test_full_attempt_scored_on_the_server(client):
    auth = register_ok(client)
    status = client.get("/api/quiz/status", headers=bearer(auth["token"])).json()
    assert status["eligible"] is True and status["quiz"]["question_count"] == 20

    started = _start(client, auth)
    assert started.status_code == 201, started.text
    body = started.json()
    assert len(body["questions"]) == 20
    assert all(set(q) == {"id", "level", "text", "options"} for q in body["questions"])
    assert "explanation" not in started.text

    answers = {qid: "B" for qid in KEY}
    result = _submit(client, auth, body["attempt_id"], answers)
    assert result.status_code == 200, result.text
    r = result.json()
    expected = sum(1 for qid, a in KEY.items() if a == "B")
    assert (r["score"], r["total"], r["correct"], r["incorrect"]) == (expected, 20, expected, 20 - expected)
    assert r["status"] == "completed" and r["duplicate"] is False and len(r["review"]) == 20

    again = _submit(client, auth, body["attempt_id"], {qid: a for qid, a in KEY.items()})
    assert again.status_code == 200 and again.json()["duplicate"] is True and again.json()["score"] == expected

    history = client.get("/api/quiz/history", headers=bearer(auth["token"])).json()
    assert history["summary"]["completed_attempts"] == 1 and history["summary"]["latest"]["score"] == expected


def test_cooldown_force_attempt_and_insufficient_wildcards(client):
    auth = register_ok(client)
    first = _start(client, auth).json()
    _submit(client, auth, first["attempt_id"], dict(KEY))

    blocked = _start(client, auth)
    assert blocked.status_code == 429 and error_of(blocked)["code"] == "COOLDOWN"
    assert "next_eligible_at" in error_of(blocked)["fields"]

    sql("UPDATE wildcard_wallets SET gift_cards = 0, default_cards = 2, last_gift_at = now() WHERE user_id = $1", auth["user_id"])
    poor = _start(client, auth, "forced")
    assert poor.status_code == 402 and error_of(poor)["code"] == "NOT_ENOUGH_WILDCARDS"

    sql("UPDATE wildcard_wallets SET default_cards = 5 WHERE user_id = $1", auth["user_id"])
    key = f"k-{uuid.uuid4().hex[:16]}"
    forced = _start(client, auth, "forced", key)
    assert forced.status_code == 201 and forced.json()["wildcards_spent"] == 3 and forced.json()["wildcards"] == 2
    retry = _start(client, auth, "forced", key)
    assert retry.status_code == 201 and retry.json()["attempt_id"] == forced.json()["attempt_id"]
    assert sql("SELECT gift_cards + default_cards FROM wildcard_wallets WHERE user_id = $1", auth["user_id"], fetch="val") == 2
    assert sql("SELECT count(*) FROM wildcard_ledger WHERE user_id = $1 AND reason = 'quiz_force'", auth["user_id"], fetch="val") == 1


def test_attempts_of_other_users_are_not_found(client):
    owner, other = register_ok(client), register_ok(client)
    attempt = _start(client, owner).json()
    for response in (
        client.get(f"/api/quiz/attempts/{attempt['attempt_id']}", headers=bearer(other["token"])),
        _submit(client, other, attempt["attempt_id"], dict(KEY)),
        client.post(f"/api/quiz/attempts/{attempt['attempt_id']}/abandon", headers=bearer(other["token"])),
    ):
        assert response.status_code == 404 and error_of(response)["code"] == "ATTEMPT_NOT_FOUND"


@pytest.mark.parametrize("payload", [
    {"mode": "normal"},                                     # no idempotency key
    {"mode": "normal", "idempotency_key": "short"},
    {"mode": "cheat", "idempotency_key": "abcdefgh123"},
])
def test_bad_start_requests_are_validation_errors(client, payload):
    auth = register_ok(client)
    response = client.post("/api/quiz/attempts", headers=bearer(auth["token"]), json=payload)
    assert response.status_code == 400 and error_of(response)["code"] == "VALIDATION_ERROR"


def test_incomplete_and_malformed_submissions(client):
    auth = register_ok(client)
    attempt = _start(client, auth).json()
    partial = _submit(client, auth, attempt["attempt_id"], {"1": "B"})
    assert partial.status_code == 400 and error_of(partial)["code"] == "INCOMPLETE"
    bad = _submit(client, auth, attempt["attempt_id"], {**KEY, "1": "Z"})
    assert bad.status_code == 400 and error_of(bad)["code"] == "VALIDATION_ERROR"
    assert client.get(f"/api/quiz/attempts/{attempt['attempt_id']}", headers=bearer(auth["token"])).json()["status"] == "in_progress"


def test_one_pending_access_request(client):
    auth = register_ok(client)
    first = client.post("/api/quiz/access-requests", headers=bearer(auth["token"]), json={"reason": "exam"})
    assert first.status_code == 201 and first.json()["status"] == "pending"
    second = client.post("/api/quiz/access-requests", headers=bearer(auth["token"]), json={"reason": "again"})
    assert second.status_code == 409 and error_of(second)["code"] == "REQUEST_EXISTS"
    mine = client.get("/api/quiz/access-requests", headers=bearer(auth["token"])).json()
    assert [r["status"] for r in mine] == ["pending"]
