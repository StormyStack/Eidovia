"""
Gateway Dependencies
`get_current_user` protects routes with `Authorization: Bearer <token>`.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import repositories as repo
from app.db import db
from app.errors import token_invalid, token_missing
from app.security import decode_access_token

# Declared so /docs shows the "Authorize" button; parsing is done below so that
# a missing header (TOKEN_MISSING) and a wrong scheme (TOKEN_INVALID) differ.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT from POST /api/auth/login")


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    username: str
    is_admin: bool


async def get_current_user(
    request: Request,
    _credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUser:
    """
    Resolve the caller from the Bearer token.

    Raises:
        ApiError: TOKEN_MISSING, TOKEN_INVALID (bad token or deleted user), TOKEN_EXPIRED
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise token_missing()

    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise token_invalid()

    user_id = decode_access_token(token)

    # Fetch user profile to get is_admin flag
    async with db.get_session() as session:
        profile = await repo.get_user_profile(session, user_id)
        if not profile:
            raise token_invalid()

    return CurrentUser(
        user_id=user_id,
        username=profile.get("username", "unknown"),
        is_admin=bool(profile.get("is_admin")),
    )
