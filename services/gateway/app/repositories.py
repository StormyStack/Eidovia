"""
Gateway Data Access
All SQL for users and modules. Uses bound parameters only (never string
formatting) and the existing tables from 01_schema.sql, plus the additive
users.email column from migrations/001_add_user_email.sql.
"""

import json
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================
# USERS
# ============================================================

async def find_user_conflicts(session: AsyncSession, username: str, email: str) -> tuple[bool, bool]:
    """Return (username_taken, email_taken), both case-insensitive."""
    result = await session.execute(
        text("""
            SELECT
                EXISTS (SELECT 1 FROM users WHERE lower(username) = lower(:username)) AS username_taken,
                EXISTS (SELECT 1 FROM users WHERE lower(email) = lower(:email))       AS email_taken
        """),
        {"username": username, "email": email},
    )
    row = result.one()
    return bool(row.username_taken), bool(row.email_taken)


async def create_user(
    session: AsyncSession, username: str, email: str, password_hash: str, language: str
) -> dict[str, Any]:
    """Insert a user; detail_level uses the schema default."""
    result = await session.execute(
        text("""
            INSERT INTO users (username, email, password_hash, language)
            VALUES (:username, :email, :password_hash, :language)
            RETURNING user_id, detail_level, language
        """),
        {"username": username, "email": email, "password_hash": password_hash, "language": language},
    )
    row = result.one()
    return {"user_id": str(row.user_id), "detail_level": row.detail_level, "language": row.language}


async def get_user_for_login(session: AsyncSession, username: str) -> Optional[Any]:
    """
    Case-insensitive lookup. If older data holds several case-variants of the
    same name, only an exact-case match is accepted (never guess).
    """
    result = await session.execute(
        text("""
            SELECT user_id, username, password_hash, detail_level, language, is_admin
            FROM users
            WHERE lower(username) = lower(:username)
        """),
        {"username": username},
    )
    rows = result.all()
    if len(rows) == 1:
        return rows[0]
    exact = [row for row in rows if row.username == username]
    return exact[0] if len(exact) == 1 else None


async def user_exists(session: AsyncSession, user_id: str) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM users WHERE user_id = :user_id"),
        {"user_id": uuid.UUID(user_id)},
    )
    return result.first() is not None


async def get_user_profile(session: AsyncSession, user_id: str) -> Optional[dict[str, Any]]:
    result = await session.execute(
        text("""
            SELECT user_id, username, email, detail_level, language, is_admin, created_at
            FROM users
            WHERE user_id = :user_id
        """),
        {"user_id": uuid.UUID(user_id)},
    )
    row = result.first()
    if row is None:
        return None
    return {
        "user_id": str(row.user_id),
        "username": row.username,
        "email": row.email,
        "detail_level": row.detail_level,
        "language": row.language,
        "is_admin": row.is_admin,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


# ============================================================
# MODULES
# ============================================================

def _as_dict(value: Any) -> dict:
    """JSONB may arrive as dict (SQLAlchemy asyncpg codec) or str; always return a dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def list_modules(session: AsyncSession) -> list[dict[str, Any]]:
    """Module list for the Home screen; display metadata lives in config.display."""
    result = await session.execute(
        text("""
            SELECT
                module_id,
                name AS title,
                COALESCE(config -> 'display' ->> 'description', '') AS description,
                difficulty,
                config -> 'display' ->> 'thumbnail_url' AS thumbnail_url
            FROM modules
            ORDER BY difficulty, module_id
        """)
    )
    return [
        {
            "module_id": row.module_id,
            "title": row.title,
            "description": row.description,
            "difficulty": row.difficulty,
            "thumbnail_url": row.thumbnail_url,
        }
        for row in result.all()
    ]


async def get_module_config(session: AsyncSession, module_id: str) -> Optional[dict[str, Any]]:
    result = await session.execute(
        text("""
            SELECT module_id, scene_name, cdn_bundle_url, difficulty, config
            FROM modules
            WHERE module_id = :module_id
        """),
        {"module_id": module_id},
    )
    row = result.first()
    if row is None:
        return None
    return {
        "module_id": row.module_id,
        "scene_name": row.scene_name,
        "cdn_bundle_url": row.cdn_bundle_url,
        "difficulty": row.difficulty,
        "config": _as_dict(row.config),
    }


async def users_email_column_exists(session: AsyncSession) -> bool:
    """True once migrations/001_add_user_email.sql has been applied."""
    result = await session.execute(
        text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'email'
        """)
    )
    return result.first() is not None
