"""
User Routes
GET /api/users/{user_id}/profile  (path from PDF; response shape NEW)
"""

import uuid

from fastapi import APIRouter, Depends

from app import errors
from app import repositories as repo
from app.db import db
from app.deps import CurrentUser, get_current_user
from app.schemas import UserProfileResponse

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
