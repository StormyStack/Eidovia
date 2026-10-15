from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from dependencies import require_admin, CurrentAdmin
from services.ar_service import ArService, MAX_GIFT


class WildcardGift(BaseModel):
    amount: int = Field(..., ge=1, le=MAX_GIFT)
    # one key per "Give" form: a double click or a retry with the same key gives the cards only once
    request_key: Optional[str] = Field(None, min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")

router = APIRouter(prefix="/ar", tags=["admin-ar-game"])


@router.get("/summary")
async def ar_summary(_admin: CurrentAdmin = Depends(require_admin)) -> dict[str, Any]:
    """AR game KPIs: players, sessions, play time, levels passed/skipped, finished journeys."""
    return await ArService.get_summary()


@router.get("/levels")
async def ar_levels(_admin: CurrentAdmin = Depends(require_admin)) -> List[dict[str, Any]]:
    """Per level: players who reached, passed and skipped it, average and best time."""
    return await ArService.get_levels()


@router.get("/players")
async def ar_players(
    search: str = Query("", max_length=100),
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """Per learner: levels passed/skipped, current level, sessions, play time, finished or not."""
    return await ArService.get_players(search)


@router.get("/players/{user_id}/events")
async def ar_player_events(
    user_id: str,
    limit: int = Query(300, ge=1, le=1000),
    _admin: CurrentAdmin = Depends(require_admin),
) -> List[dict[str, Any]]:
    """One learner's AR timeline, newest first."""
    return await ArService.get_player_events(user_id, limit)


@router.post("/players/{user_id}/wildcards")
async def ar_give_wildcards(
    user_id: str,
    body: WildcardGift,
    admin: CurrentAdmin = Depends(require_admin),
) -> dict[str, Any]:
    """Give a learner 1-10 wildcards (added to their default cards). Admins can only give, never take."""
    result = await ArService.grant_wildcards(user_id, body.amount, admin.username, body.request_key, admin)
    if result is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    return result
