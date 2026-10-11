"""
Eidovia AI service: HOE depth-capped RAG with a local LLM (Phi-4 mini via Ollama).
REST: /api/chat. WebSocket: /ws/adapt/{session_id}.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional
from uuid import uuid4

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config
from app.bandit import bandit
from app.cache import cache_service
from app.database import db
from app.events import EventRequest, event_service
from app.llm import llm_client
from app.rag import rag_service
from app.scheduler import scheduler

logger = logging.getLogger(__name__)

# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Eidovia Service",
    description="Adaptive learning with HOE-capped RAG, local LLM, and Redis cache",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# RESPONSE TEXT
# ============================================================

SCOPE_MESSAGE = (
    "I appreciate your question, but it appears to be outside the scope "
    "of the current curriculum. Please ask questions related to DNA and "
    "cell biology."
)
GREETING_MESSAGE = (
    "Hello! I'm your AI tutor for DNA and cell biology. Ask me about "
    "the curriculum, for example: how does DNA replication work?"
)
GREETINGS = {
    "hi", "hello", "hey", "good morning", "good afternoon",
    "good evening", "thanks", "thank you",
}
VALID_LEVELS = {None, 1, 2, 3, 4}


def _is_greeting(text_in: str) -> bool:
    return text_in.strip().lower().rstrip("!.?") in GREETINGS


# ============================================================
# PYDANTIC MODELS
# ============================================================

class ChatRequest(BaseModel):
    """hoe_level caps retrieval depth (1 to 4). Omit it for no cap."""
    question: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    module_id: Optional[str] = None
    hoe_level: Optional[int] = Field(default=None, ge=1, le=4)


class ChatResponse(BaseModel):
    answer: str
    is_on_topic: bool
    max_similarity: float
    num_documents: int
    latency_ms: float
    decision_id: Optional[str] = None
    cached: bool = False
    hoe_level: Optional[int] = None
    # Chunks that were actually retrieved at this depth (for evaluation)
    retrieved: list[dict] = []
    # Chunks that were shown to the user as the basis of the answer
    sources: list[dict] = []


class CacheStatsResponse(BaseModel):
    hits: int
    misses: int
    errors: int
    total: int
    hit_rate: str
    redis_status: str


# ============================================================
# LIFECYCLE
# ============================================================

@app.on_event("startup")
async def startup():
    logger.info("=" * 70)
    logger.info("Eidovia SERVICE STARTUP")
    logger.info("=" * 70)

    await cache_service.connect()
    logger.info("Redis cache connected")

    await db.connect()
    logger.info("Database connected")

    await rag_service.initialize()
    logger.info(f"RAG ready (embeddings: {rag_service.backend})")

    # scheduler is intentionally not started yet (ETL job not implemented)
    logger.info(f"LLM: {config.LLM_MODEL} at {config.LLM_BASE_URL} (mock={config.MOCK_LLM})")
    logger.info("=" * 70)


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down services...")
    try:
        await cache_service.close()
        await scheduler.stop()
        await llm_client.close()
        await rag_service.close()
        await db.disconnect()
        logger.info("Cleanup complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# ============================================================
# HEALTH AND CACHE
# ============================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "eidovia-ai",
        "version": "1.0.0",
        "database": "connected" if db.is_healthy else "disconnected",
        "cache": "connected" if cache_service.client else "disconnected",
        "rag_ready": rag_service.ready,
        "embed_backend": rag_service.backend,
        "scheduler_running": scheduler.running,
        "llm_model": config.LLM_MODEL,
        "mock_llm": config.MOCK_LLM,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/cache-stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    stats = cache_service.get_stats()
    return CacheStatsResponse(
        hits=stats["hits"],
        misses=stats["misses"],
        errors=stats["errors"],
        total=stats["total"],
        hit_rate=stats["hit_rate"],
        redis_status="connected" if cache_service.client else "disconnected",
    )


@app.post("/api/cache-flush")
async def flush_cache():
    success = await cache_service.flush()
    return {
        "success": success,
        "message": "Cache flushed" if success else "Failed to flush cache",
    }


# ============================================================
# SHARED CHAT PIPELINE (used by REST and WebSocket)
# ============================================================

async def _run_chat(question: str, hoe_level: Optional[int]) -> dict:
    start = time.time()

    if hoe_level not in VALID_LEVELS:
        raise ValueError("hoe_level must be 1 to 4, or omitted")

    if _is_greeting(question):
        return {
            "answer": GREETING_MESSAGE,
            "is_on_topic": False,
            "max_similarity": 0.0,
            "num_documents": 0,
            "latency_ms": (time.time() - start) * 1000,
            "decision_id": None,
            "cached": False,
            "hoe_level": hoe_level,
            "retrieved": [],
            "sources": [],
        }

    query_embedding = await rag_service.encode_query(question)

    async with db.get_session() as session:
        documents = await rag_service.retrieve_capped(
            session, query_embedding, max_level=hoe_level
        )

    max_similarity = max((d["similarity"] for d in documents), default=0.0)
    is_on_topic = bool(documents)
    shown: list[dict] = []

    if not documents:
        answer = SCOPE_MESSAGE
    elif config.MOCK_LLM:
        answer = "Based on the curriculum:\n\n" + "\n\n".join(
            f"[{d['title']}] {d['content']}" for d in documents
        )
        shown = documents
    else:
        try:
            text_out = await llm_client.generate(question, documents, hoe_level)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            text_out = None

        if text_out is None:
            answer = "The AI tutor is temporarily unavailable. Please try again shortly."
        elif "NOT_IN_CURRICULUM" in text_out:
            answer = SCOPE_MESSAGE
        else:
            # Sources come from the chunks actually sent, never from the model
            titles = list(dict.fromkeys(d["title"] for d in documents))
            answer = text_out + "\n\nSources: " + ", ".join(titles)
            shown = documents

    decision_id = None
    try:
        state_vector = np.array([
            1.0 if is_on_topic else 0.0,
            min(max_similarity, 1.0),
            len(documents) / 10.0,
            0.5, 0.5, 0.5, 0.5, 0.5,  # placeholders until real signals are wired
        ])
        bandit.select_action(state_vector)
        decision_id = str(uuid4())
    except Exception as e:
        logger.warning(f"Bandit decision failed: {e}")

    latency_ms = (time.time() - start) * 1000
    logger.info(
        f"Response (hoe_level={hoe_level}, docs={len(documents)}, "
        f"latency={latency_ms:.0f}ms)"
    )

    def _summary(docs: list[dict]) -> list[dict]:
        return [
            {
                "title": d["title"],
                "hoe_level": d["hoe_level"],
                "similarity": round(d["similarity"], 3),
            }
            for d in docs
        ]

    return {
        "answer": answer,
        "is_on_topic": is_on_topic,
        "max_similarity": max_similarity,
        "num_documents": len(documents),
        "latency_ms": latency_ms,
        "decision_id": decision_id,
        "cached": False,
        "hoe_level": hoe_level,
        "retrieved": _summary(documents),
        "sources": _summary(shown),
    }


VALID_LEVELS = {None, 1, 2, 3, 4}


# ============================================================
# CHAT (REST)
# ============================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        result = await _run_chat(request.question, request.hoe_level)
    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
    return ChatResponse(**result)


# ============================================================
# WEBSOCKET (ADAPTIVE)
# ============================================================

@app.websocket("/ws/adapt/{session_id}")
async def websocket_adapt(websocket: WebSocket, session_id: str):
    """
    Client sends: {"question": "...", "hoe_level": 1-4 (optional)}
    Server replies with the same fields as /api/chat, plus session_id.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: {session_id}")

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
            question = (data.get("question") or "").strip()
            hoe_level = data.get("hoe_level")

            if not question:
                await websocket.send_json({
                    "error": "No question provided",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            try:
                result = await _run_chat(question, hoe_level)
                await websocket.send_json({
                    **result,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                logger.error(f"WS processing failed: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                })

    except asyncio.TimeoutError:
        logger.warning(f"WS timeout: {session_id}")
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        logger.info(f"WS disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WS error: {e}")
        await websocket.close(code=1011)


# ============================================================
# EVENT LOGGING
# ============================================================

@app.post("/api/events", response_model=dict)
async def log_event(event: EventRequest):
    try:
        async with db.get_session() as session:
            event_id = await event_service.log_event(session, event)
            return {
                "status": "logged",
                "event_id": event_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
    except Exception as e:
        logger.error(f"Event logging failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Eidovia",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat (POST, optional hoe_level 1-4)",
            "websocket": "/ws/adapt/{session_id} (WebSocket)",
            "cache_stats": "/api/cache-stats (GET)",
            "cache_flush": "/api/cache-flush (POST)",
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, workers=1)