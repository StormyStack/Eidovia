from typing import Any
from fastapi import APIRouter, Depends, Query
from dependencies import require_admin, CurrentAdmin
from services.account_service import AccountService

# Users section (app learners) and Administrators section, kept apart by users.is_admin.
# Changes (edit, reset password, delete, give wildcards) use the existing routes: /admin/users/... and
# /admin/ar/players/{id}/wildcards. Every route here needs an administrator (require_admin).
router = APIRouter(prefix="/accounts", tags=["admin-accounts"])


@router.get("/users")
async def list_app_users(
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Regular application users only, newest first, paginated."""
    return await AccountService.list_accounts(False, q, page, page_size)


@router.get("/admins")
async def list_administrators(
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Administrator accounts only."""
    out = await AccountService.list_accounts(True, q, page, page_size)
    for item in out["items"]:
        item["is_you"] = item["user_id"] == str(admin.user_id)
    return out


@router.get("/users/{user_id}")
async def user_profile(user_id: str, _admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    """One user's profile: details, sign-in status, usage, wildcards, quiz summary, IPs and devices."""
    return await AccountService.user_profile(user_id)


@router.get("/users/{user_id}/wildcards")
async def user_wildcards(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Wallet now and the wildcard ledger (grants, daily gifts, earned and spent cards)."""
    return await AccountService.wildcard_history(user_id, limit)


@router.get("/users/{user_id}/activity")
async def user_activity_log(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    date_from: str = Query("", max_length=40),
    date_to: str = Query("", max_length=40),
    category: str = Query("", pattern="^(|account|chat|ar|wildcard|quiz|other|admin)$"),
    status: str = Query("", pattern="^(|success|failed)$"),
    ip: str = Query("", max_length=64),
    q: str = Query("", max_length=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """The user's activity log: what, when (server time), from which IP and device, status, and the admin if any."""
    return await AccountService.activity(user_id, page, page_size, date_from, date_to, category, status, ip, q)
