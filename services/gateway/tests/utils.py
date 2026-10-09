"""Shared helpers for gateway tests."""

import asyncio
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
import bcrypt
import jwt

PASSWORD = "Correct-Horse-9"


def unique_username(prefix: str = "user") -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _connect_kwargs(database: Optional[str] = None) -> dict:
    return {
        "host": os.environ["DATABASE_HOST"],
        "port": int(os.environ["DATABASE_PORT"]),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": database or os.environ["POSTGRES_DB"],
    }


def sql(query: str, *args: Any, database: Optional[str] = None, fetch: str = "none") -> Any:
    """Run one statement directly against a test database (separate connection)."""
    async def _run():
        conn = await asyncpg.connect(**_connect_kwargs(database))
        try:
            if fetch == "row":
                return await conn.fetchrow(query, *args)
            if fetch == "all":
                return await conn.fetch(query, *args)
            if fetch == "val":
                return await conn.fetchval(query, *args)
            return await conn.execute(query, *args)
        finally:
            await conn.close()
    return asyncio.run(_run())


def register(client, username: Optional[str] = None, email: Optional[str] = None,
             password: str = PASSWORD, **extra):
    username = username or unique_username()
    payload = {"username": username, "email": email or f"{username}@example.com", "password": password, **extra}
    return client.post("/api/auth/register", json=payload)


def register_ok(client, **kwargs) -> dict:
    response = register(client, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_token(sub: Any, secret: Optional[str] = None, minutes: int = 60,
               include_exp: bool = True, include_iat: bool = True) -> str:
    """Craft a JWT for negative tests (expired, wrong secret, bad subject...)."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(sub)}
    if include_iat:
        payload["iat"] = now
    if include_exp:
        payload["exp"] = now + timedelta(minutes=minutes)
    return jwt.encode(payload, secret or os.environ["JWT_SECRET"], algorithm="HS256")


def insert_user(username: str, password: str = PASSWORD, email: Optional[str] = None,
                password_hash: Optional[str] = None) -> str:
    """Insert a user directly (simulates rows created by other team tooling)."""
    hashed = password_hash or bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()
    user_id = sql(
        "INSERT INTO users (username, email, password_hash) VALUES ($1, $2, $3) RETURNING user_id",
        username, email, hashed, fetch="val",
    )
    return str(user_id)


def error_of(response) -> dict:
    """Return the contract error object, asserting the shape on the way."""
    body = response.json()
    assert set(body) == {"detail"}, body
    detail = body["detail"]
    assert isinstance(detail.get("code"), str) and isinstance(detail.get("message"), str), detail
    return detail


def new_uuid() -> str:
    return str(uuid.uuid4())
