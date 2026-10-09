"""POST /api/auth/register and POST /api/auth/login — success + every error case."""

import logging
import os
import uuid

import jwt
import pytest

from app import repositories
from tests.utils import (
    PASSWORD, error_of, insert_user, register, register_ok, sql, unique_username,
)

AUTH_KEYS = {"user_id", "token", "profile"}


# ============================================================
# REGISTER — success
# ============================================================

def test_register_returns_login_shape_and_valid_token(client):
    username = unique_username("Reg")
    response = register(client, username=username)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == AUTH_KEYS
    assert body["profile"] == {"detail_level": 1, "language": "en"}
    uuid.UUID(body["user_id"])

    claims = jwt.decode(body["token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["sub"] == body["user_id"]
    assert claims["exp"] > claims["iat"]


def test_register_stores_bcrypt_hash_and_lowercase_email(client):
    username = unique_username()
    body = register_ok(client, username=username, email=f"  {username.upper()}@Example.COM ")

    row = sql("SELECT username, email, password_hash FROM users WHERE user_id = $1",
              uuid.UUID(body["user_id"]), fetch="row")
    assert row["username"] == username
    assert row["email"] == f"{username}@example.com"
    assert row["password_hash"].startswith("$2b$")
    assert PASSWORD not in row["password_hash"]


def test_register_accepts_language(client):
    body = register_ok(client, language="bn")
    assert body["profile"]["language"] == "bn"


# ============================================================
# REGISTER — 400 validation
# ============================================================

@pytest.mark.parametrize("change, field, message_part", [
    ({"username": None}, "username", "required"),
    ({"email": None}, "email", "required"),
    ({"password": None}, "password", "required"),
    ({"username": "ab"}, "username", "3 to 32"),
    ({"username": "x" * 33}, "username", "3 to 32"),
    ({"username": "bad name!"}, "username", "letters"),
    ({"username": "   "}, "username", "required"),
    ({"email": "not-an-email"}, "email", "valid email"),
    ({"email": "a@b"}, "email", "valid email"),
    ({"password": "short"}, "password", "at least 8"),
    ({"password": "p" * 73}, "password", "at most 72"),
    ({"password": "é" * 37}, "password", "at most 72"),   # 74 bytes in UTF-8
    ({"language": "english"}, "language", "2-letter"),
    ({"username": 12345}, "username", "text"),
])
def test_register_validation_errors(client, change, field, message_part):
    username = unique_username()
    payload = {"username": username, "email": f"{username}@example.com", "password": PASSWORD}
    for key, value in change.items():
        if value is None:
            payload.pop(key)
        else:
            payload[key] = value

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    detail = error_of(response)
    assert detail["code"] == "VALIDATION_ERROR"
    assert message_part.lower() in detail["fields"][field].lower()
    assert "WWW-Authenticate" not in response.headers


def test_register_empty_body_lists_every_required_field(client):
    response = client.post("/api/auth/register", json={})
    assert response.status_code == 400
    assert set(error_of(response)["fields"]) == {"username", "email", "password"}


def test_register_malformed_json_is_400(client):
    response = client.post("/api/auth/register", content="{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert error_of(response)["code"] == "VALIDATION_ERROR"


def test_validation_error_never_echoes_password(client):
    response = client.post("/api/auth/register", json={"username": "ab", "email": "x", "password": "secret1"})
    assert "secret1" not in response.text


# ============================================================
# REGISTER — 409 conflicts
# ============================================================

def test_register_duplicate_username_case_insensitive(client):
    username = unique_username("Dup")
    register_ok(client, username=username)

    response = register(client, username=username.upper(), email=f"other_{username}@example.com")
    assert response.status_code == 409
    detail = error_of(response)
    assert detail["code"] == "USERNAME_TAKEN"
    assert "username" in detail["fields"]


def test_register_duplicate_email_case_insensitive(client):
    username = unique_username()
    register_ok(client, username=username)

    response = register(client, username=unique_username(), email=f"{username.upper()}@EXAMPLE.com")
    assert response.status_code == 409
    assert error_of(response)["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize("taken", ["username", "email"])
def test_register_race_condition_maps_db_conflict_to_409(client, monkeypatch, taken):
    """If two sign-ups race past the pre-check, the DB unique index still yields a clean 409."""
    existing = register_ok(client)
    existing_name = sql("SELECT username FROM users WHERE user_id = $1",
                        uuid.UUID(existing["user_id"]), fetch="val")

    async def no_conflicts(*args, **kwargs):
        return False, False
    monkeypatch.setattr(repositories, "find_user_conflicts", no_conflicts)

    if taken == "username":
        response = register(client, username=existing_name, email=f"fresh_{existing_name}@example.com")
        expected = "USERNAME_TAKEN"
    else:
        response = register(client, username=unique_username(), email=f"{existing_name}@example.com")
        expected = "EMAIL_TAKEN"

    assert response.status_code == 409
    assert error_of(response)["code"] == expected


# ============================================================
# LOGIN — success
# ============================================================

def test_login_returns_exact_pdf_shape(client):
    username = unique_username()
    registered = register_ok(client, username=username, language="bn")

    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == AUTH_KEYS
    assert set(body["profile"]) == {"detail_level", "language"}
    assert body["user_id"] == registered["user_id"]
    assert body["profile"] == {"detail_level": 1, "language": "bn"}
    claims = jwt.decode(body["token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["sub"] == registered["user_id"]


def test_login_username_is_case_insensitive_and_trimmed(client):
    username = unique_username("Case")
    register_ok(client, username=username)
    response = client.post("/api/auth/login", json={"username": f"  {username.swapcase()} ", "password": PASSWORD})
    assert response.status_code == 200


def test_login_exact_case_wins_when_legacy_case_variants_exist(client):
    base = unique_username("Mixed")
    upper_id = insert_user(base)
    insert_user(base.lower())

    exact = client.post("/api/auth/login", json={"username": base, "password": PASSWORD})
    assert exact.status_code == 200
    assert exact.json()["user_id"] == upper_id

    ambiguous = client.post("/api/auth/login", json={"username": base.upper(), "password": PASSWORD})
    assert ambiguous.status_code == 401


# ============================================================
# LOGIN — errors
# ============================================================

def test_login_wrong_password_and_unknown_user_are_indistinguishable(client):
    username = unique_username()
    register_ok(client, username=username)

    wrong_password = client.post("/api/auth/login", json={"username": username, "password": "Wrong-Pass-1"})
    unknown_user = client.post("/api/auth/login", json={"username": unique_username(), "password": PASSWORD})

    for response in (wrong_password, unknown_user):
        assert response.status_code == 401
        assert error_of(response)["code"] == "INVALID_CREDENTIALS"
        assert response.headers["WWW-Authenticate"] == "Bearer"
    assert wrong_password.json() == unknown_user.json()


@pytest.mark.parametrize("payload, field", [
    ({"username": "someone"}, "password"),
    ({"password": PASSWORD}, "username"),
    ({"username": "   ", "password": PASSWORD}, "username"),
    ({"username": "someone", "password": ""}, "password"),
])
def test_login_missing_fields_is_400(client, payload, field):
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 400
    detail = error_of(response)
    assert detail["code"] == "VALIDATION_ERROR"
    assert field in detail["fields"]


def test_login_with_non_bcrypt_stored_hash_is_401_not_500(client):
    username = unique_username("legacy")
    insert_user(username, password_hash="plain-text-not-a-hash")
    response = client.post("/api/auth/login", json={"username": username, "password": "plain-text-not-a-hash"})
    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_CREDENTIALS"


def test_login_with_overlong_password_is_401_not_500(client):
    username = unique_username()
    register_ok(client, username=username)
    response = client.post("/api/auth/login", json={"username": username, "password": "p" * 500})
    assert response.status_code == 401


# ============================================================
# SECURITY — logs
# ============================================================

def test_passwords_and_tokens_are_never_logged(client, caplog):
    caplog.set_level(logging.DEBUG)
    username = unique_username()
    secret_password = "Very-Secret-Pass-42"

    body = register_ok(client, username=username, password=secret_password)
    login = client.post("/api/auth/login", json={"username": username, "password": secret_password})
    client.post("/api/auth/login", json={"username": username, "password": "Wrong-Secret-99"})

    assert login.status_code == 200
    assert secret_password not in caplog.text
    assert "Wrong-Secret-99" not in caplog.text
    assert body["token"] not in caplog.text
    assert login.json()["token"] not in caplog.text
