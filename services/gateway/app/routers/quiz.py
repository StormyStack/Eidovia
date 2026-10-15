"""
DNA quiz routes for the mobile app (rules: app/quiz_service.py).

GET  /api/quiz/status                      eligibility, cooldown, active attempt, wildcards, requests
POST /api/quiz/attempts                    start {mode: normal|forced|authorized, idempotency_key}
GET  /api/quiz/attempts/{attempt_id}       resume an attempt (questions) or read its result
POST /api/quiz/attempts/{attempt_id}/submit   {answers: {question id: "A".."D"}} → scored on the server
POST /api/quiz/attempts/{attempt_id}/abandon
GET  /api/quiz/history                     the user's attempts + summary (dashboard)
POST /api/quiz/access-requests             ask an admin to take the quiz before the cooldown ends {reason}
GET  /api/quiz/access-requests             the user's requests and their status

Every route needs a login and only ever touches the caller's own data.
"""

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import quiz_service as quiz
from app.db import db
from app.deps import CurrentUser, get_current_user
from app.errors import ApiError
from app.logger_client import push_log_event
from app.routers.wildcards import log_daily_gift

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


def _api_error(e: quiz.QuizError) -> ApiError:
    """Contract error format; extra facts (e.g. next_eligible_at, attempt_id) travel as string fields."""
    extra = {k: (",".join(v) if isinstance(v, list) else str(v)) for k, v in e.extra.items() if v is not None}
    return ApiError(e.status, e.code, e.message, extra or None)


async def _log(user: CurrentUser, action: str, details: dict) -> None:
    if details:
        await push_log_event(action, user.user_id, user.username, user.is_admin, details)


@router.get("/status")
async def quiz_status(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with db.get_session() as session:
        out = await quiz.status(session, current_user.user_id)
    await log_daily_gift(current_user, out.pop("_wallet"), out.pop("_daily_gift"))
    return out


class StartRequest(BaseModel):
    mode: Literal["normal", "forced", "authorized"] = "normal"
    idempotency_key: str = Field(..., min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")


@router.post("/attempts", status_code=201)
async def start_attempt(body: StartRequest, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        async with db.get_session() as session:
            out, event = await quiz.start(session, current_user.user_id, current_user.username,
                                          body.mode, body.idempotency_key)
    except quiz.QuizError as e:
        raise _api_error(e)
    await _log(current_user, "quiz_started", event)
    return out


@router.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: str, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        async with db.get_session() as session:
            return await quiz.get_attempt(session, current_user.user_id, attempt_id)
    except quiz.QuizError as e:
        raise _api_error(e)


class SubmitRequest(BaseModel):
    answers: Any


@router.post("/attempts/{attempt_id}/submit")
async def submit_attempt(attempt_id: str, body: SubmitRequest,
                         current_user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        async with db.get_session() as session:
            out, event = await quiz.submit(session, current_user.user_id, attempt_id, body.answers)
    except quiz.QuizError as e:
        raise _api_error(e)
    await _log(current_user, "quiz_completed", event)
    return out


@router.post("/attempts/{attempt_id}/abandon")
async def abandon_attempt(attempt_id: str, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        async with db.get_session() as session:
            out, event = await quiz.abandon(session, current_user.user_id, attempt_id)
    except quiz.QuizError as e:
        raise _api_error(e)
    await _log(current_user, "quiz_abandoned", event)
    return out


@router.get("/history")
async def quiz_history(limit: int = Query(50, ge=1, le=200),
                       current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with db.get_session() as session:
        return await quiz.history(session, current_user.user_id, limit)


class AccessRequestBody(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


@router.post("/access-requests", status_code=201)
async def create_access_request(body: AccessRequestBody,
                                current_user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        async with db.get_session() as session:
            out, event = await quiz.create_request(session, current_user.user_id, current_user.username, body.reason)
    except quiz.QuizError as e:
        raise _api_error(e)
    await _log(current_user, "quiz_access_requested", event)
    return out


@router.get("/access-requests")
async def my_access_requests(current_user: CurrentUser = Depends(get_current_user)) -> list:
    async with db.get_session() as session:
        return await quiz.list_requests(session, current_user.user_id)
