"""
User Routes
GET   /api/users/{user_id}/profile  (path from PDF; response shape NEW)
GET   /api/users/me                 the app's Profile page: name, email, level, age, gender
PATCH /api/users/me                 change email, level, age, gender
POST  /api/users/me/password        change password (needs the current one)
"""

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app import errors
from app import repositories as repo
from app.db import db
from app.deps import CurrentUser, get_current_user
from app.logger_client import push_log_event
from app.schemas import EMAIL_MAX, EMAIL_PATTERN, PASSWORD_MIN, UserProfileResponse
from app.security import BCRYPT_MAX_BYTES, hash_password, verify_password

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
async def get_profile(user_id: str, current_user: CurrentUser = Depends(get_current_user)) -> UserProfileResponse:
    """Return the caller's own profile; other users' profiles are forbidden."""
    try:
        requested_id = str(uuid.UUID(user_id))
    except ValueError:
        raise errors.validation_error({"user_id": "Must be a valid user ID."})

    if requested_id != current_user.user_id:
        raise errors.forbidden()

    async with db.get_session() as session:
        profile = await repo.get_user_profile(session, requested_id)

    if profile is None:
        # get_current_user already confirmed the user exists; only a concurrent delete gets here
        raise errors.token_invalid()

    return UserProfileResponse(**profile)



# ============================================================
# PROFILE PAGE (the signed-in user only)
# ============================================================

GENDERS = ("male", "female", "other", "prefer_not_to_say")
LEVELS = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}   # users.detail_level (also how detailed AI answers are)

PROFILE_COLUMNS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS age INT CHECK (age IS NULL OR age BETWEEN 5 AND 120)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT",
]
_columns_ready = False


async def _ensure_columns(session) -> None:
    """Migration 009 adds age/gender on a fresh database; older databases get them here."""
    global _columns_ready
    if not _columns_ready:
        for sql in PROFILE_COLUMNS:
            await session.execute(text(sql))
        _columns_ready = True


async def _me(session, user_id: str) -> dict:
    row = (await session.execute(text("""
        SELECT user_id, username, email, detail_level, language, age, gender, created_at FROM users WHERE user_id = :u
    """), {"u": uuid.UUID(user_id)})).first()
    if row is None:
        raise errors.token_invalid()
    return {
        "user_id": str(row.user_id),
        "username": row.username,
        "email": row.email,
        "level": row.detail_level,
        "level_name": LEVELS.get(row.detail_level, f"Level {row.detail_level}"),
        "language": row.language,
        "age": row.age,
        "gender": row.gender,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with db.get_session() as session:
        await _ensure_columns(session)
        return await _me(session, current_user.user_id)


class ProfileUpdate(BaseModel):
    """Only the fields that are sent change. age / gender may be set to null to clear them."""
    email: Optional[str] = None
    level: Optional[int] = Field(None, ge=1, le=3)
    age: Optional[int] = Field(None, ge=5, le=120)
    gender: Optional[Literal["male", "female", "other", "prefer_not_to_say"]] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if len(value) > EMAIL_MAX or not EMAIL_PATTERN.match(value):
            raise ValueError("Enter a valid email address.")
        return value


@router.patch("/me")
async def update_me(body: ProfileUpdate, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    changes = body.model_dump(exclude_unset=True)
    columns = {"email": "email", "level": "detail_level", "age": "age", "gender": "gender"}
    async with db.get_session() as session:
        await _ensure_columns(session)
        if changes.get("email"):
            taken = (await session.execute(text(
                "SELECT 1 FROM users WHERE lower(email) = :e AND user_id <> :u"
            ), {"e": changes["email"], "u": uuid.UUID(current_user.user_id)})).first()
            if taken:
                raise errors.email_taken()
        if "email" in changes and changes["email"] is None:
            del changes["email"]                       # email cannot be removed
        if changes:
            sets = ", ".join(f"{columns[k]} = :{k}" for k in changes)
            await session.execute(text(f"UPDATE users SET {sets} WHERE user_id = :u"),
                                  {**changes, "u": uuid.UUID(current_user.user_id)})
        profile = await _me(session, current_user.user_id)
    if changes:
        await push_log_event("profile_updated", current_user.user_id, current_user.username, current_user.is_admin,
                             {"changed": sorted(changes), **{k: v for k, v in changes.items() if k != "email"}})
    return profile


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new(cls, value: str) -> str:
        if len(value) < PASSWORD_MIN:
            raise ValueError(f"Password must be at least {PASSWORD_MIN} characters.")
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError("Password is too long.")
        return value


@router.post("/me/password")
async def change_password(body: PasswordChange, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with db.get_session() as session:
        row = (await session.execute(text("SELECT password_hash FROM users WHERE user_id = :u"),
                                     {"u": uuid.UUID(current_user.user_id)})).first()
    if row is None or not await verify_password(body.current_password, row.password_hash):
        raise errors.validation_error({"current_password": "Current password is not correct."},
                                      "Current password is not correct.")
    if body.current_password == body.new_password:
        raise errors.validation_error({"new_password": "Choose a password different from the current one."},
                                      "Choose a password different from the current one.")
    new_hash = await hash_password(body.new_password)
    async with db.get_session() as session:
        await session.execute(text("UPDATE users SET password_hash = :h WHERE user_id = :u"),
                              {"h": new_hash, "u": uuid.UUID(current_user.user_id)})
    await push_log_event("password_changed", current_user.user_id, current_user.username, current_user.is_admin, {})
    return {"status": "password_changed"}
