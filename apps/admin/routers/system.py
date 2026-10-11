from typing import List, Any
from fastapi import APIRouter, Depends, status
from dependencies import require_admin, CurrentAdmin
from schemas import SystemAnnouncementCreate, SystemAnnouncementResponse, SystemHealthResponse
from services.system_service import SystemService

router = APIRouter(prefix="/system", tags=["admin-system"])


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Comprehensive system health diagnostics (PostgreSQL, Redis, Ollama)."""
    return await SystemService.get_system_health()


@router.post("/cache/flush")
async def flush_cache(
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Purge Redis hot answer caches to force fresh generative model responses."""
    return await SystemService.flush_cache()


@router.get("/announcements", response_model=List[SystemAnnouncementResponse])
async def list_announcements(
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """List system maintenance and platform notices."""
    return await SystemService.list_announcements()


@router.post("/announcements", response_model=SystemAnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    body: SystemAnnouncementCreate,
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Publish a system-wide banner notice or maintenance advisory."""
    return await SystemService.create_announcement(body)
