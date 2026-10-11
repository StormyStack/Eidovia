from typing import List, Any
from fastapi import APIRouter, Depends, Query, WebSocket
from dependencies import require_admin, CurrentAdmin
from schemas import PlatformStatsResponse
from services.audit_service import AuditService

router = APIRouter(tags=["admin-audit"])


@router.get("/stats", response_model=PlatformStatsResponse)
async def get_stats(
    _admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Retrieve platform KPI aggregates: users, messages, logs, tickets."""
    return await AuditService.get_platform_stats()


@router.get("/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=500),
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """Retrieve historical audit logs."""
    return await AuditService.get_logs(limit=limit)


@router.websocket("/ws")
async def websocket_logs(websocket: WebSocket, token: str):
    """Realtime WebSocket logs for admin console."""
    await AuditService.handle_websocket_logs(websocket, token)
