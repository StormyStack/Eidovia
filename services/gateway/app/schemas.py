"""
Gateway Request/Response Models
Shapes follow docs/api-auth-home.md exactly. Response models also act as a
filter: FastAPI drops any field not declared here, so no extra keys leak out.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.security import BCRYPT_MAX_BYTES

USERNAME_MIN, USERNAME_MAX = 3, 32
PASSWORD_MIN = 8
EMAIL_MAX = 254
DEFAULT_LANGUAGE = "en"

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}$")

REQUIRED = "This field is required."


# ============================================================
# REQUESTS
# ============================================================

class RegisterRequest(BaseModel):
    """POST /api/auth/register"""
    username: str
    email: str
    password: str
    # validate_default: pydantic v2 skips validators for defaults, which would leave None (NOT NULL column)
    language: Optional[str] = Field(default=None, validate_default=True)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(REQUIRED)
        if not USERNAME_MIN <= len(value) <= USERNAME_MAX:
            raise ValueError(f"Username must be {USERNAME_MIN} to {USERNAME_MAX} characters.")
        if not USERNAME_PATTERN.match(value):
            raise ValueError("Use only letters, numbers, underscores (_), dots (.) and hyphens (-).")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError(REQUIRED)
        if len(value) > EMAIL_MAX or not EMAIL_PATTERN.match(value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        # Never strip or otherwise alter passwords
        if not value:
            raise ValueError(REQUIRED)
        if len(value) < PASSWORD_MIN:
            raise ValueError(f"Password must be at least {PASSWORD_MIN} characters.")
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} characters.")
        return value

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: Optional[str]) -> str:
        if value is None or value.strip() == "":
            return DEFAULT_LANGUAGE
        value = value.strip()
        if not LANGUAGE_PATTERN.match(value):
            raise ValueError("Use a 2-letter lowercase language code, e.g. \"en\".")
        return value


class LoginRequest(BaseModel):
    """POST /api/auth/login (PDF contract: { username, password })"""
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(REQUIRED)
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value:
            raise ValueError(REQUIRED)
        return value


# ============================================================
# RESPONSES
# ============================================================

class ProfileSummary(BaseModel):
    detail_level: int
    language: str


class AuthResponse(BaseModel):
    """Login and register response (PDF contract)."""
    user_id: str
    token: str
    profile: ProfileSummary


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str]
    detail_level: int
    language: str
    created_at: str


class ModuleListItem(BaseModel):
    module_id: str
    title: str
    description: str
    difficulty: int
    thumbnail_url: Optional[str]


class ModuleConfigResponse(BaseModel):
    """GET /api/modules/{id}/config (PDF contract)."""
    module_id: str
    scene_name: str
    cdn_bundle_url: str
    difficulty: int
    config: dict


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
