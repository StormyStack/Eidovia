from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from dependencies import require_admin, CurrentAdmin
from services.quiz_admin_service import QuizAdminService

router = APIRouter(prefix="/quiz", tags=["admin-quiz"])


@router.get("/summary")
async def quiz_summary(_admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    """Aggregate quiz statistics (completed attempts only for results; see services/quiz_admin_service.py)."""
    return await QuizAdminService.summary()


@router.get("/requests")
async def quiz_requests(
    status: str = Query("", pattern="^(|pending|approved|rejected|used|expired)$"),
    user: str = Query("", max_length=100),
    date_from: str = Query("", max_length=40),
    date_to: str = Query("", max_length=40),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Access requests, pending first. Filter by status, user and creation date."""
    return await QuizAdminService.list_requests(status, user, date_from, date_to, page, page_size)


class Approve(BaseModel):
    window_start: Optional[str] = Field(None, max_length=40)
    window_end: Optional[str] = Field(None, max_length=40)
    cooldown_hours: Optional[int] = Field(None, ge=0, le=168)
    reason: Optional[str] = Field(None, max_length=500)


class Reject(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str, body: Approve, admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    """Authorize ONE quiz start in the window (default now → +24 h) with its own cooldown (default 12 h)."""
    return await QuizAdminService.decide(request_id, admin, True, body.reason, body.window_start, body.window_end,
                                         body.cooldown_hours)


@router.post("/requests/{request_id}/reject")
async def reject_request(request_id: str, body: Reject, admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    return await QuizAdminService.decide(request_id, admin, False, body.reason)


@router.get("/attempts")
async def quiz_attempts(
    user: str = Query("", max_length=100),
    date_from: str = Query("", max_length=40),
    date_to: str = Query("", max_length=40),
    min_percent: Optional[float] = Query(None, ge=0, le=100),
    max_percent: Optional[float] = Query(None, ge=0, le=100),
    attempt_type: str = Query("", pattern="^(|normal|forced|authorized)$"),
    status: str = Query("completed", pattern="^(completed|incomplete|abandoned|expired|in_progress|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Quiz log, newest first, paginated. Default: completed results only."""
    return await QuizAdminService.list_attempts(user, date_from, date_to, min_percent, max_percent, attempt_type,
                                                status, page, page_size)


@router.get("/attempts/{attempt_id}")
async def quiz_attempt(attempt_id: str, _admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    return await QuizAdminService.attempt_detail(attempt_id)


@router.get("/users")
async def quiz_users(
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Per-user performance summary (from completed attempts) with cooldown and wildcard use."""
    return await QuizAdminService.list_users(search, page, page_size)


@router.get("/users/{user_id}")
async def quiz_user(user_id: str, _admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    return await QuizAdminService.user_detail(user_id)
