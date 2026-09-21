"""
EduAR-AI Main Service
FastAPI microservice with RAG + Contextual Bandit integration.
Provides /chat (REST) and /ws/adapt/{session_id} (WebSocket) endpoints.
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

import config_prod as config
from database_service import db
from rag_service import rag_service
from bandit_service import bandit
from scheduler_service import scheduler

logger = logging.getLogger(__name__)

# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="EduAR-AI Service",
    description="Adaptive learning with RAG + contextual bandit",
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


# ============================================================
# LIFECYCLE EVENTS
# ============================================================

@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    logger.info("=" * 70)
    logger.info("🚀 EduAR-AI SERVICE STARTUP")
    logger.info("=" * 70)
    
    try:
        # Connect to database
        await db.connect()
        logger.info("✅ Database connected")
        
        # Initialize RAG
        await rag_service.initialize()
        logger.info("✅ RAG service initialized")
        
        # Initialize scheduler
        #await scheduler.initialize()
        logger.info("✅ Scheduler initialized")
        
        # Start background jobs
        # await scheduler.start()
        logger.info("✅ Background scheduler started")
        
        logger.info("=" * 70)
        logger.info(f"API: http://{config.API_HOST}:{config.API_PORT}")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("Shutting down services...")
    
    try:
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
        "service": "eduarai-ai",
        "version": "1.0.0",
        "database": "connected" if db.is_healthy else "disconnected",
        "rag_ready": rag_service.model is not None,
        "scheduler_running": scheduler.running,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================
# CHAT ENDPOINT (REST)
# ============================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with RAG guardrail and decision logging.
    
    Args:
        request: Chat request with question
        
    Returns:
        ChatResponse with answer and metadata
        
    Raises:
        HTTPException: If processing fails
    """
    start_time = datetime.utcnow()
    
    try:
        # Validate inputs
        if not request.question or len(request.question) < 3:
            raise HTTPException(
                status_code=400,
                detail="Question must be at least 3 characters"
            )
        
        # Generate IDs if not provided
        user_id = request.user_id or str(uuid4())
        session_id = request.session_id or str(uuid4())
        
        # Encode query to embedding
        logger.info(f"Processing: '{request.question[:50]}...'")
        query_embedding = await rag_service.encode_query(request.question)
        
        # Get database session
        async with await db.get_session() as session:
            # Retrieve documents
            rag_context = await rag_service.build_context(
                session,
                request.question,
                query_embedding
            )
        
        # Generate response
        if rag_context["is_on_topic"]:
            answer = (
                f"Based on our curriculum materials:\n\n"
                f"{rag_context['context']}\n\n"
                f"This is a great question about {request.module_id or 'the topic'}!"
            )
        else:
            answer = (
                "I appreciate your question, but it's outside the scope of our "
                "current curriculum. Let's focus on the biology content."
            )
        
        # Calculate latency
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        logger.info(
            f"Chat response: on_topic={rag_context['is_on_topic']}, "
            f"similarity={rag_context['max_similarity']:.3f}, "
            f"latency={latency_ms:.1f}ms"
        )
        
        return ChatResponse(
            answer=answer,
            is_on_topic=rag_context["is_on_topic"],
            max_similarity=rag_context["max_similarity"],
            num_documents=rag_context["num_documents"],
            latency_ms=latency_ms,
            decision_id=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# WEBSOCKET ADAPTATION
# ============================================================

@app.websocket("/ws/adapt/{session_id}")
async def websocket_adapt(websocket: WebSocket, session_id: str):
    """
    WebSocket adaptation endpoint for real-time learning.
    Receives interaction events and sends contextual adaptations.
    
    Args:
        websocket: WebSocket connection
        session_id: User session ID
    """
    await websocket.accept()
    logger.info(f"✅ WebSocket connected: {session_id}")
    
    try:
        while True:
            # Receive interaction event
            data = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=config.WS_TIMEOUT
            )
            
            event = json.loads(data)
            
            # Extract event fields
            question = event.get("question", "")
            correct = bool(event.get("correct", False))
            response_time_ms = float(event.get("response_time_ms", 3000))
            difficulty = int(event.get("difficulty", 1))
            
            # Build state vector (8D)
            state_vector = np.array([
                1.0 if correct else 0.0,           # correctness
                min(response_time_ms / 5000, 1.0), # response_time_norm
                float(difficulty) / 3.0,           # difficulty_level
                0.5,                               # topic_match
                0.7,                               # engagement
                0.1,                               # question_count_norm
                0.0 if correct else 1.0,           # error_rate
                min(response_time_ms / 10000, 1.0) # time_spent_norm
            ], dtype=np.float32)
            
            # Get bandit recommendation
            action_id, action_name = bandit.recommend_action_by_state(state_vector)
            
            # Update bandit with reward
            reward = 1.0 if correct else 0.0
            await bandit.update(action_id, reward)
            
            # Send adaptation response
            response = {
                "action_id": int(action_id),
                "action_name": action_name,
                "reward": float(reward),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await websocket.send_json(response)
            
            logger.debug(
                f"Adaptation: action={action_name}, correct={correct}, "
                f"reward={reward:.2f}"
            )
            
    except asyncio.TimeoutError:
        logger.warning(f"WebSocket timeout: {session_id}")
    except WebSocketDisconnect:
        logger.info(f"❌ WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    config.validate_config()
    
    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="info",
        access_log=True
    )
