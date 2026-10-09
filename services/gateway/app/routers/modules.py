"""
Module Routes
GET /api/modules                    (path from architecture diagram; response shape NEW)
GET /api/modules/{module_id}/config (PDF contract, exact)
"""

from fastapi import APIRouter, Depends

from app import errors
from app import repositories as repo
from app.db import db
from app.deps import CurrentUser, get_current_user
from app.schemas import ModuleConfigResponse, ModuleListItem

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleListItem])
async def list_modules(_: CurrentUser = Depends(get_current_user)) -> list[ModuleListItem]:
    """All AR modules, ordered by difficulty then module_id ([] when none exist)."""
    async with db.get_session() as session:
        modules = await repo.list_modules(session)
    return [ModuleListItem(**module) for module in modules]


@router.get("/{module_id}/config", response_model=ModuleConfigResponse)
async def get_module_config(module_id: str, _: CurrentUser = Depends(get_current_user)) -> ModuleConfigResponse:
    """Config handed to ARGameScreen (and, from Sprint 2, to Unity via UnityBridge)."""
    async with db.get_session() as session:
        config = await repo.get_module_config(session, module_id)
    if config is None:
        raise errors.module_not_found()
    return ModuleConfigResponse(**config)
