"""GET /api/users/{user_id}/profile and the Bearer-token dependency."""

from datetime import datetime

import pytest

from tests.utils import (
    bearer, error_of, insert_user, make_token, new_uuid, register_ok, sql, unique_username,
)

PROFILE_KEYS = {"user_id", "username", "email", "detail_level", "language", "created_at"}


def _profile(client, user_id, headers):
    return client.get(f"/api/users/{user_id}/profile", headers=headers)


def test_profile_returns_own_profile(client):
    username = unique_username("Prof")
    auth = register_ok(client, username=username, language="bn")

    response = _profile(client, auth["user_id"], bearer(auth["token"]))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == PROFILE_KEYS
    assert body["user_id"] == auth["user_id"]
    assert body["username"] == username
    assert body["email"] == f"{username.lower()}@example.com"
    assert body["detail_level"] == 1
    assert body["language"] == "bn"
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None


def test_profile_email_is_null_for_users_created_without_email(client):
    user_id = insert_user(unique_username("noemail"))
    response = _profile(client, user_id, bearer(make_token(user_id)))
    assert response.status_code == 200
    assert response.json()["email"] is None


# ============================================================
# 401 — token problems
# ============================================================

def test_missing_token_is_401_token_missing(client):
    response = _profile(client, new_uuid(), headers={})
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_MISSING"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", [
    "Bearer not-a-jwt",
    "Bearer ",
    "Basic dXNlcjpwYXNz",
    "Token abc.def.ghi",
])
def test_malformed_authorization_is_401_token_invalid(client, authorization):
    response = _profile(client, new_uuid(), headers={"Authorization": authorization})
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_INVALID"


def test_wrong_signature_is_401_token_invalid(client):
    auth = register_ok(client)
    forged = make_token(auth["user_id"], secret="a-different-secret-that-is-long-enough-123")
    response = _profile(client, auth["user_id"], bearer(forged))
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_INVALID"


@pytest.mark.parametrize("token_kwargs", [
    {"sub": "not-a-uuid"},
    {"include_exp": False},
    {"include_iat": False},
])
def test_token_with_bad_claims_is_401_token_invalid(client, token_kwargs):
    auth = register_ok(client)
    kwargs = dict(token_kwargs)
    sub = kwargs.pop("sub", auth["user_id"])
    response = _profile(client, auth["user_id"], bearer(make_token(sub, **kwargs)))
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_INVALID"


def test_expired_token_is_401_token_expired(client):
    auth = register_ok(client)
    expired = make_token(auth["user_id"], minutes=-5)
    response = _profile(client, auth["user_id"], bearer(expired))
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_EXPIRED"


def test_token_of_deleted_user_is_401_token_invalid(client):
    auth = register_ok(client)
    sql("DELETE FROM users WHERE user_id = $1::uuid", auth["user_id"])
    response = _profile(client, auth["user_id"], bearer(auth["token"]))
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_INVALID"


# ============================================================
# 403 / 400
# ============================================================

def test_other_users_profile_is_403(client):
    me = register_ok(client)
    other = register_ok(client)
    for target in (other["user_id"], new_uuid()):
        response = _profile(client, target, bearer(me["token"]))
        assert response.status_code == 403
        assert error_of(response)["code"] == "FORBIDDEN"


def test_non_uuid_user_id_is_400(client):
    me = register_ok(client)
    response = _profile(client, "not-a-uuid", bearer(me["token"]))
    assert response.status_code == 400
    detail = error_of(response)
    assert detail["code"] == "VALIDATION_ERROR"
    assert "user_id" in detail["fields"]


def test_auth_is_checked_before_path_validation(client):
    response = _profile(client, "not-a-uuid", headers={})
    assert response.status_code == 401
