from typing import List, Optional, Any
from fastapi import APIRouter, Depends, Query, status
from dependencies import require_admin, CurrentAdmin
from schemas import AdminUserCreate, AdminUserUpdate, AdminPasswordReset, UserProfileResponse
from services.user_service import UserService

router = APIRouter(prefix="/users", tags=["admin-users"])


@router.get("", response_model=List[UserProfileResponse])
async def list_users(
    q: Optional[str] = Query(None, description="Search term for username or email"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """List registered users with optional search filter."""
    return await UserService.list_users(q=q, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=dict[str, Any])
async def get_user_details(
    user_id: str,
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Retrieve full profile and telemetry summary for a user."""
    return await UserService.get_user(user_id)


@router.post("", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Provision a new student or administrative account."""
    return await UserService.create_user(body)


@router.patch("/{user_id}", response_model=UserProfileResponse)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Update profile attributes or modify role privileges for a user."""
    return await UserService.update_user(user_id, body, current_admin_id=str(admin.user_id))


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    body: AdminPasswordReset,
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, str]:
    """Administrative password reset."""
    return await UserService.reset_password(user_id, body)


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, str]:
    """Permanently delete a user account and associated sessions."""
    return await UserService.delete_user(user_id, current_admin_id=str(admin.user_id))
