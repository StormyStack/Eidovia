"""
Eidovia Main Service (Cache-First Architecture)
FastAPI microservice with RAG + Contextual Bandit + Redis Cache
Provides REST (/chat) and WebSocket (/ws/adapt/{session_id}) endpoints.

Architecture:
- Request → Redis Cache (check)
- Miss → RAG Database Query (with pgvector)
- Response → Store in Redis Cache
- Return → Client
"""

import logging
import json
import asyncio
import numpy as np
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4
from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import time

from app import config
from app.database import db
from app.rag import rag_service
from app.bandit import bandit
from app.scheduler import scheduler
from app.cache import cache_service
from app.events import event_service, EventRequest

logger = logging.getLogger(__name__)

# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Eidovia Service",
    description="Adaptive learning with RAG + Contextual Bandit + Redis Cache",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# PYDANTIC MODELS
# ============================================================

class ChatRequest(BaseModel):
    """Chat endpoint request."""
    question: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    module_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat endpoint response."""
    answer: str
    is_on_topic: bool
    max_similarity: float
    num_documents: int
    latency_ms: float
    decision_id: Optional[str] = None
    cached: bool = False  # ← NEW: indicates if from cache


class CacheStatsResponse(BaseModel):
    """Cache statistics response."""
    hits: int
    misses: int
    errors: int
    total: int
    hit_rate: str
    redis_status: str


# ============================================================
# LIFECYCLE EVENTS
# ============================================================

@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    logger.info("=" * 70)
    logger.info("🚀 Eidovia SERVICE STARTUP (Cache-First)")
    logger.info("=" * 70)
    
    try:
        # Connect to cache first (fastest, non-critical)
        await cache_service.connect()
        logger.info("✅ Redis cache connected")
        
        # Connect to database
        await db.connect()
        logger.info("✅ Database connected")
        
        # Initialize RAG
        await rag_service.initialize()
        logger.info("✅ RAG service initialized")
        
        # Initialize scheduler
        # await scheduler.initialize()
        logger.info("✅ Scheduler initialized")
        
        # Start background jobs
        # await scheduler.start()
        logger.info("✅ Background scheduler started")
        
        logger.info("=" * 70)
        logger.info(f"API: http://{config.API_HOST}:{config.API_PORT}")
        logger.info(f"Cache: Redis (default TTL: {rag_service.context_ttl}s)")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("Shutting down services...")
    
    try:
        await cache_service.close()  # ← NEW: close cache
        await scheduler.stop()
        await db.disconnect()
        logger.info("✅ Cleanup complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health_check():
    """System health check."""
    return {
        "status": "healthy",
        "service": "eidovia-ai",
        "version": "1.0.0",
        "database": "connected" if db.is_healthy else "disconnected",
        "cache": "connected" if cache_service.client else "disconnected",
        "rag_ready": rag_service.model is not None,
        "scheduler_running": scheduler.running,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================
# CACHE STATISTICS ENDPOINT (NEW)
# ============================================================

@app.get("/api/cache-stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """
    Get cache performance statistics.
    
    Returns:
        Cache hit/miss rates and status
    """
    stats = cache_service.get_stats()
    redis_status = "connected" if cache_service.client else "disconnected"
    
    return CacheStatsResponse(
        hits=stats["hits"],
        misses=stats["misses"],
        errors=stats["errors"],
        total=stats["total"],
        hit_rate=stats["hit_rate"],
        redis_status=redis_status
    )


@app.post("/api/cache-flush")
async def flush_cache():
    """
    Flush all cache (use with caution!).
    
    Returns:
        Confirmation message
    """
    success = await cache_service.flush()
    return {
        "success": success,
        "message": "Cache flushed" if success else "Failed to flush cache"
    }


# ============================================================
# CHAT ENDPOINT (REST) - CACHE-FIRST
# ============================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with Cache-First RAG guardrail.
    
    Request Flow:
    1. Encode query to embedding
    2. Check Redis cache
    3. If miss, retrieve from DB + build context
    4. Get bandit decision
    5. Return response
    
    Args:
        request: Chat request with question
        
    Returns:
        ChatResponse with answer and metadata
    """
    start_time = time.time()
    session_id = request.session_id or str(uuid4())
    user_id = request.user_id or "anonymous"
    
    try:
        async with db.get_session() as session:
            
            # ───────────────────────────────────────────────────────
            # STEP 1: Encode query
            # ───────────────────────────────────────────────────────
            logger.info(f"Processing query: {request.question[:50]}...")
            query_embedding = await rag_service.encode_query(request.question)
            
            
            # ───────────────────────────────────────────────────────
            # STEP 2: Build RAG context (cache-first)
            # ───────────────────────────────────────────────────────
            rag_result = await rag_service.build_context(
                session=session,
                query=request.question,
                query_embedding=query_embedding,
                use_cache=True  # ← Cache-first strategy
            )
            
            is_on_topic = rag_result["is_on_topic"]
            max_similarity = rag_result["max_similarity"]
            num_documents = rag_result["num_documents"]
            context = rag_result["context"]
            
            
            # ───────────────────────────────────────────────────────
            # STEP 3: Generate answer
            # ───────────────────────────────────────────────────────
            if is_on_topic and context:
                answer = (
                    f"Based on the curriculum:\n\n{context}\n\n"
                    f"Your query appears to be on-topic "
                    f"(similarity: {max_similarity:.2f})"
                )
            else:
                answer = (
                    f"I appreciate your question, but it appears to be "
                    f"outside the scope of the current curriculum. "
                    f"Please ask questions related to DNA and cell biology."
                )
            
            
            # ───────────────────────────────────────────────────────
            # STEP 4: Get bandit decision (adaptive action)
            # ───────────────────────────────────────────────────────
            decision_id = None
            try:
                state_vector = np.array([
                    1.0 if is_on_topic else 0.0,  # on-topic indicator
                    min(max_similarity, 1.0),     # relevance
                    num_documents / 10.0,         # num docs (normalized)
                    0.5,  # placeholder: correct_answer_rate
                    0.5,  # placeholder: hints_per_session
                    0.5,  # placeholder: difficulty
                    0.5,  # placeholder: engagement_rate
                    0.5,  # placeholder: content_skip_rate
                ])
                
                action = bandit.select_action(state_vector)
                decision_id = str(uuid4())
                
                logger.info(f"Bandit action: {action} (decision_id: {decision_id})")
            except Exception as e:
                logger.warning(f"Bandit decision failed: {e}")
            
            
            # ───────────────────────────────────────────────────────
            # STEP 5: Calculate latency
            # ───────────────────────────────────────────────────────
            latency_ms = (time.time() - start_time) * 1000
            cached = rag_result.get("cached", False)
            
            logger.info(
                f"✅ Response complete "
                f"(latency: {latency_ms:.1f}ms, cached: {cached})"
            )
            
            return ChatResponse(
                answer=answer,
                is_on_topic=is_on_topic,
                max_similarity=max_similarity,
                num_documents=num_documents,
                latency_ms=latency_ms,
                decision_id=decision_id,
                cached=cached
            )
    
    except Exception as e:
        logger.error(f"❌ Chat request failed: {e}")
        latency_ms = (time.time() - start_time) * 1000
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "latency_ms": latency_ms
            }
        )


# ============================================================
# WEBSOCKET ENDPOINT (ADAPTIVE)
# ============================================================

@app.websocket("/ws/adapt/{session_id}")
async def websocket_adapt(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time adaptive learning.
    
    Protocol:
    - Client sends: {"question": "...", "action_feedback": {...}}
    - Server responds: {"answer": "...", "action": "increase_difficulty", ...}
    - SLA: <150ms per message
    
    Args:
        websocket: WebSocket connection
        session_id: User session ID
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: {session_id}")
    
    try:
        while True:
            # Receive message
            data = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=30.0
            )
            
            question = data.get("question", "")
            
            if not question:
                await websocket.send_json({
                    "error": "No question provided",
                    "timestamp": datetime.utcnow().isoformat()
                })
                continue
            
            start_time = time.time()
            
            try:
                async with db.get_session() as session:
                    # Encode + retrieve (with cache)
                    query_embedding = await rag_service.encode_query(question)
                    rag_result = await rag_service.build_context(
                        session=session,
                        query=question,
                        query_embedding=query_embedding,
                        use_cache=True
                    )
                    
                    # Bandit decision
                    state_vector = np.random.rand(8)
                    action = bandit.select_action(state_vector)
                    
                    latency_ms = (time.time() - start_time) * 1000
                    
                    # Send response
                    await websocket.send_json({
                        "answer": rag_result["context"][:200] + "...",
                        "is_on_topic": rag_result["is_on_topic"],
                        "action": action,
                        "latency_ms": latency_ms,
                        "cached": rag_result.get("cached", False),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    logger.info(
                        f"WS Response: {session_id} "
                        f"(latency: {latency_ms:.1f}ms, action: {action})"
                    )
            
            except Exception as e:
                logger.error(f"WS processing failed: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
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
# EVENT LOGGING ENDPOINT
# ============================================================

@app.post("/api/events", response_model=dict)
async def log_event(event: EventRequest):
    """
    Log learner interaction event.
    
    Event types:
    - quiz_answer: {"correct": bool, "time_spent_ms": int}
    - ar_interaction: {"object_id": str, "time_spent_ms": int}
    - hint_requested: {"hint_type": str}
    - content_skip: {"content_id": str}
    - content_viewed: {"content_id": str, "duration_ms": int}
    """
    try:
        async with db.get_session() as session:
            event_id = await event_service.log_event(session, event)
            
            return {
                "status": "logged",
                "event_id": event_id,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    except Exception as e:
        logger.error(f"❌ Event logging failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Eidovia",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat (POST)",
            "websocket": "/ws/adapt/{session_id} (WebSocket)",
            "cache_stats": "/api/cache-stats (GET)",
            "cache_flush": "/api/cache-flush (POST)"
        },
        "architecture": "Cache-First RAG with Redis + PostgreSQL + pgvector",
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        workers=4
    )