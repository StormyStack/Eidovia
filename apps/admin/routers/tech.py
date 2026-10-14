from typing import Any, List
from fastapi import APIRouter, Depends, Query
from dependencies import require_admin, CurrentAdmin
from services.tech_service import TechService

router = APIRouter(prefix="/tech", tags=["admin-technical"])


@router.get("/status")
async def tech_status(_admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    """Every service up or down, logged-in / active users, traffic and errors in the last hour."""
    return await TechService.get_status()


@router.get("/online")
async def tech_online(_admin: CurrentAdmin = Depends(require_admin)) -> List[dict[str, Any]]:
    """Users logged in right now with their IP, device and last request."""
    return await TechService.get_logged_in()


@router.get("/requests")
async def tech_requests(
    limit: int = Query(300, ge=1, le=2000),
    user: str = Query("", max_length=100),
    kind: str = Query("all", pattern="^(all|errors|server|slow|chat)$"),
    q: str = Query("", max_length=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """Technical application log: every gateway request (who, IP, device, path, upstream, status, time), newest first."""
    return await TechService.get_requests(limit, user, kind, q)
