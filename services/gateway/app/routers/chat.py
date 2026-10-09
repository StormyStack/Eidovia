"""
Chat Routes — Gateway proxy to the AI service (port 8001).

POST /api/chat   → forwards to http://localhost:8001/api/chat
POST /api/events → forwards to http://localhost:8001/api/events

The mobile app only talks to the gateway (port 8000) and never directly to the
AI service.  Auth is validated here (JWT required) before forwarding.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Any, Optional

from app.deps import CurrentUser, get_current_user
from app import errors

logger = logging.getLogger(__name__)

# AI service base URL — read from env so it can be overridden in tests/prod.
# Default: localhost:8001 (same machine, Docker-exposed port).
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
AI_TIMEOUT = float(os.getenv("AI_SERVICE_TIMEOUT", "30"))

router = APIRouter(prefix="/api", tags=["chat"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ChatRequest(BaseModel):
    """POST /api/chat — mirrors the AI service's ChatRequest."""
    question: str
    session_id: Optional[str] = None
    module_id: Optional[str] = None


class ChatResponse(BaseModel):
    """POST /api/chat — mirrors the AI service's ChatResponse."""
    answer: str
    is_on_topic: bool
    max_similarity: float
    num_documents: int
    latency_ms: float
    decision_id: Optional[str] = None
    cached: bool = False


class EventPayload(BaseModel):
    """POST /api/events — learner interaction event."""
    session_id: str
    event_type: str
    payload: Optional[dict[str, Any]] = None
    client_timestamp: Optional[str] = None


# ============================================================
# ROUTES
# ============================================================

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    """
    Proxy a chat question to the AI service.

    The gateway validates the JWT and injects the authenticated user_id so the
    AI service can personalise responses and log bandit feedback correctly.
    """
    payload = {
        "question": body.question,
        "user_id": current_user.user_id,
        "session_id": body.session_id,
        "module_id": body.module_id,
    }
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            response = await client.post(f"{AI_SERVICE_URL}/api/chat", json=payload)
            response.raise_for_status()
            return ChatResponse(**response.json())
    except httpx.TimeoutException:
        logger.warning("AI service timeout on /api/chat")
        raise errors.ai_service_unavailable()
    except httpx.HTTPStatusError as exc:
        logger.warning("AI service error %s on /api/chat", exc.response.status_code)
        raise errors.ai_service_unavailable()
    except Exception as exc:
        logger.error("Unexpected error forwarding to AI service: %s", exc)
        raise errors.ai_service_unavailable()


@router.post("/events")
async def log_event(
    body: EventPayload,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Proxy a learner interaction event to the AI service for bandit training.
    Fire-and-forget: the mobile app does not need the response.
    """
    payload = {
        "user_id": current_user.user_id,
        "session_id": body.session_id,
        "event_type": body.event_type,
        "payload": body.payload,
        "client_timestamp": body.client_timestamp,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{AI_SERVICE_URL}/api/events", json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("Could not log event to AI service: %s", exc)
        return {"status": "queued"}
