"""
Eidovia Gateway Configuration
Reads settings from environment variables (and apps/gateway/.env if present).

Database variable names are the SAME as the AI service's config_prod.py
(POSTGRES_USER, DB_PASSWORD, POSTGRES_DB, DATABASE_HOST, DATABASE_PORT),
so the whole team can share one set of database credentials.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from urllib.parse import quote_plus

GATEWAY_ROOT = Path(__file__).resolve().parent.parent
# Unified root .env lives at Thesis/.env — three directories above this file.
# Set the GATEWAY_ENV_FILE env-var to override (e.g. in CI or Docker).
DEFAULT_ENV_FILE = GATEWAY_ROOT.parent.parent / ".env"

MIN_JWT_SECRET_LENGTH = 32


def _load_env_file() -> None:
    """Load apps/gateway/.env (or GATEWAY_ENV_FILE) without overriding real env vars."""
    env_file = os.getenv("GATEWAY_ENV_FILE", str(DEFAULT_ENV_FILE))
    if env_file and Path(env_file).is_file():
        load_dotenv(env_file, override=False)


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Safely retrieve environment variable with validation (same helper as config_prod.py)."""
    value = os.getenv(key, default)
    if (value is None or value == "") and required:
        raise ValueError(f"Required environment variable not set: {key}")
    return value or default


# ============================================================
# SETTINGS
# ============================================================

@dataclass(frozen=True)
class Settings:
    """Immutable gateway settings, built once from the environment."""

    # Database (shared names with config_prod.py)
    database_host: str
    database_port: int
    database_user: str
    database_password: str
    database_name: str
    db_pool_size: int
    db_max_overflow: int

    # Auth
    jwt_secret: str
    jwt_algorithm: str
    jwt_expires_minutes: int
    bcrypt_rounds: int

    # API
    host: str
    port: int

    # Redis for logger & cache
    redis_host: str
    redis_port: int
    redis_password: str

    @property
    def database_url(self) -> str:
        escaped_user = quote_plus(self.database_user)
        escaped_pw = quote_plus(self.database_password)
        return (
            f"postgresql+asyncpg://{escaped_user}:{escaped_pw}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Build settings from the environment (cached).
    Tests call get_settings.cache_clear() after changing env vars.

    Raises:
        ValueError: If a required variable is missing or invalid
    """
    _load_env_file()

    jwt_secret = get_env("JWT_SECRET", required=True)
    if len(jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise ValueError(
            f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters long"
        )

    bcrypt_rounds = int(get_env("BCRYPT_ROUNDS", "12"))
    if not 4 <= bcrypt_rounds <= 15:
        raise ValueError("BCRYPT_ROUNDS must be between 4 and 15")

    return Settings(
        database_host=get_env("DATABASE_HOST", "eidovia_postgres"),
        database_port=int(get_env("DATABASE_PORT", "5432")),
        database_user=get_env("POSTGRES_USER", "appuser"),
        database_password=get_env("DB_PASSWORD", required=True),
        database_name=get_env("POSTGRES_DB", "eidovia"),
        db_pool_size=int(get_env("DB_POOL_SIZE", "5")),
        db_max_overflow=int(get_env("DB_MAX_OVERFLOW", "10")),
        jwt_secret=jwt_secret,
        jwt_algorithm="HS256",
        jwt_expires_minutes=int(get_env("JWT_EXPIRES_MINUTES", "10080")),
        bcrypt_rounds=bcrypt_rounds,
        host=get_env("GATEWAY_HOST", "127.0.0.1"),
        port=int(get_env("GATEWAY_PORT", "8000")),
        redis_host=get_env("REDIS_HOST", "eidovia_redis"),
        redis_port=int(get_env("REDIS_PORT", "6379")),
        redis_password=get_env("REDIS_PASSWORD", required=True),
    )
