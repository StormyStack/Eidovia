"""
Chat Routes — Gateway AI Messaging via Ollama (Port 11434).

POST /api/chat   → Communicates directly with Ollama on port 11434
POST /api/events → Logs learner telemetry events

Port 11434 handles AI messaging directly without needing port 8001.
"""

import logging
import os
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import CurrentUser, get_current_user
from app.cache import redis_cache
from app.logger_client import push_log_event

logger = logging.getLogger(__name__)

# Ollama configuration (port 11434)
OLLAMA_URL = os.getenv("OLLAMA_URL", os.getenv("LLM_BASE_URL", "http://localhost:11434")).rstrip("/")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "phi4-mini")
AI_TIMEOUT = float(os.getenv("AI_SERVICE_TIMEOUT", "60"))

# Optional fallback to legacy AI microservice on port 8001 if available
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001").rstrip("/")

SYSTEM_PROMPT = """You are Eidovia AI, an interactive educational tutor specialized EXCLUSIVELY in DNA, genetics, and molecular biology.

Strict rules:
1. ONLY answer questions related to DNA and molecular biology (DNA structure, double helix, nucleotides, base pairing, DNA replication, DNA polymerase, helicase, ligase, transcription, translation, mRNA, mutations, chromosomes, and gene expression).
2. If the user sends a greeting (like "hello", "hi", "hey"), greet them warmly and invite them to ask a question about DNA and genetics.
3. If the user asks about ANYTHING outside of DNA and molecular genetics (e.g. general knowledge, other subjects, non-biology topics), DO NOT answer the question. Instead, reply strictly with:
"I appreciate your question, but I am specifically designed to tutor on DNA and molecular genetics. Please ask a question related to DNA structure, replication, enzymes, or gene expression!"
4. For valid DNA questions, give a clear, accurate, and encouraging explanation in 2 to 4 sentences directly addressing the student's question."""

router = APIRouter(prefix="/api", tags=["chat"])


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ChatRequest(BaseModel):
    """POST /api/chat — matches Mobile App request schema."""
    question: str
    session_id: Optional[str] = None
    module_id: Optional[str] = None


class ChatResponse(BaseModel):
    """POST /api/chat — matches Mobile App response schema."""
    answer: str
    is_on_topic: bool = True
    max_similarity: float = 1.0
    num_documents: int = 1
    latency_ms: float = 0.0
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
    Handle biology Q&A using Ollama (port 11434).
    """
    t0 = time.perf_counter()

    # 0. Check Redis for Hot Message (Instant ~2ms response)
    hot = await redis_cache.get_hot_message(body.question)
    if hot:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        await push_log_event(
            "message_sent",
            current_user.user_id,
            current_user.username,
            current_user.is_admin,
            {"question": body.question, "latency_ms": latency_ms, "cached": True},
        )
        return ChatResponse(
            answer=hot["answer"],
            is_on_topic=hot.get("is_on_topic", True),
            max_similarity=1.0 if hot.get("is_on_topic", True) else 0.0,
            num_documents=1 if hot.get("is_on_topic", True) else 0,
            latency_ms=latency_ms,
            cached=True,
        )

    # 1. Primary path: query Ollama on port 11434 with fast generation parameters
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": body.question},
            ],
            "options": {
                "temperature": 0.5,
                "num_predict": 120,   # Caps generation to fast, concise responses
                "num_ctx": 1024,       # Fits completely into GPU VRAM
            },
        }
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("message", {}).get("content", "").strip()
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                is_on_topic = "specifically designed to tutor on DNA" not in answer
                
                # Save as Hot Message in Redis
                await redis_cache.set_hot_message(body.question, {"answer": answer, "is_on_topic": is_on_topic})

                await push_log_event(
                    "message_sent",
                    current_user.user_id,
                    current_user.username,
                    current_user.is_admin,
                    {"question": body.question, "latency_ms": latency_ms, "cached": False},
                )

                return ChatResponse(
                    answer=answer,
                    is_on_topic=is_on_topic,
                    max_similarity=1.0 if is_on_topic else 0.0,
                    num_documents=1 if is_on_topic else 0,
                    latency_ms=latency_ms,
                    cached=False,
                )
    except Exception as exc:
        logger.info("Direct Ollama call on %s failed: %s", OLLAMA_URL, exc)

    # 2. Secondary fallback: query port 8001 if active
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{AI_SERVICE_URL}/api/chat",
                json={
                    "question": body.question,
                    "user_id": current_user.user_id,
                    "session_id": body.session_id,
                    "module_id": body.module_id,
                },
            )
            if resp.status_code == 200:
                resp_data = resp.json()
                await push_log_event(
                    "message_sent",
                    current_user.user_id,
                    current_user.username,
                    current_user.is_admin,
                    {"question": body.question, "latency_ms": resp_data.get("latency_ms")},
                )
                return ChatResponse(**resp_data)
    except Exception:
        pass

    # 3. Graceful fallback message if Ollama is still pulling or starting up
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    await push_log_event(
        "message_sent",
        current_user.user_id,
        current_user.username,
        current_user.is_admin,
        {"question": body.question, "latency_ms": latency_ms, "fallback": True},
    )
    return ChatResponse(
        answer=(
            "Hello! I am your Eidovia biology tutor. Port 11434 (Ollama) is being connected. "
            "Please make sure the Ollama container is running with 'phi4-mini' pulled."
        ),
        is_on_topic=True,
        max_similarity=0.0,
        num_documents=0,
        latency_ms=latency_ms,
        cached=False,
    )


@router.post("/events")
async def log_event(
    body: EventPayload,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Log learner interaction telemetry.
    """
    logger.debug("Logged event: %s for user %s", body.event_type, current_user.user_id)
    return {"status": "ok"}


@router.post("/cache-flush")
async def cache_flush() -> dict:
    """
    Flush all hot messages from Redis cache.
    """
    deleted = await redis_cache.flush_hot_messages()
    return {"status": "cleared", "deleted_keys": deleted}

