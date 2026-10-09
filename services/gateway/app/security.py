"""
Gateway Security
bcrypt password hashing + JWT (HS256) issue/verify.
Passwords and tokens are never logged.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt

from app.config import get_settings
from app.errors import token_expired, token_invalid

logger = logging.getLogger(__name__)

BCRYPT_MAX_BYTES = 72  # bcrypt ignores/rejects anything beyond 72 bytes


# ============================================================
# PASSWORDS
# ============================================================

def _hash_password_sync(password: str, rounds: int) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def _verify_password_sync(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        # Stored value is not a bcrypt hash (e.g. inserted by other tooling)
        logger.warning("Stored password hash is not a valid bcrypt hash")
        return False


async def hash_password(password: str) -> str:
    """Hash a password with bcrypt (runs in a worker thread: bcrypt is CPU-bound)."""
    return await asyncio.to_thread(_hash_password_sync, password, get_settings().bcrypt_rounds)


async def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt comparison (runs in a worker thread)."""
    return await asyncio.to_thread(_verify_password_sync, password, password_hash)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hash_password_sync("timing-equaliser-not-a-real-password", get_settings().bcrypt_rounds)


async def burn_password_check(password: str) -> None:
    """
    Spend the same time as a real check when the username does not exist,
    so response timing does not reveal which usernames are registered.
    """
    await verify_password(password, _dummy_hash())


# ============================================================
# JWT
# ============================================================

def create_access_token(user_id: str) -> str:
    """Issue a signed JWT whose subject is the user's UUID."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """
    Verify signature + expiry and return the user_id (sub).

    Raises:
        ApiError: TOKEN_EXPIRED or TOKEN_INVALID
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise token_expired()
    except jwt.InvalidTokenError:
        raise token_invalid()

    subject = payload.get("sub")
    try:
        return str(uuid.UUID(str(subject)))
    except ValueError:
        raise token_invalid()
