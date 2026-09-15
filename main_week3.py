#!/usr/bin/env python3
"""
Week 3 FastAPI: Real-Time Adaptation with Contextual Bandit
Features:
- RAG-based chat (from Week 2)
- Contextual bandit for personalization (Thompson sampling)
- WebSocket for real-time decisions
- Pilot study data collection
"""

import logging
import time
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from config_week2 import API_HOST, API_PORT, USE_MOCK_LLM, MOCK_RESPONSES
from config_week3 import ACTIONS, STATE_FEATURES
from rag_week2 import get_rag
from bandit_week3 import get_bandit, get_user_state

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-service-week3")

# Pydantic models
class ChatRequest(BaseModel):
    question: str
    session_id: str = None
    user_id: str = None

class ChatResponse(BaseModel):
    answer: str
    is_on_topic: bool
    sources: int
    context_used: bool
    latency_ms: float
    mock: bool = True

class InteractionEvent(BaseModel):
    user_id: str
    session_id: str
    question: str
    correct: bool
    response_time_ms: float
    topic: str = None
    difficulty: int = None

class AdaptationResponse(BaseModel):
    user_id: str
    action_id: int
    action_name: str
    action_description: str
    recommended_difficulty: int
    recommended_topic: str
    user_state: dict
    timestamp: str

# Create FastAPI app
app = FastAPI(
    title="EduAR-AI Engineer - Week 3",
    description="AI tutor with RAG + Contextual Bandit for personalization",
    version="0.3.0"
)

# Add CORS for WebSocket
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get instances
rag = get_rag()
bandit = get_bandit()

# ============================================================
# HTTP ENDPOINTS (from Week 2)
# ============================================================

@app.get("/health")
async def health():
    """Health check"""
    chunks_loaded = len(rag.chunks) if rag.chunks else 0
    
    return {
        "status": "healthy",
        "service": "ai-service-week3",
        "version": "0.3.0",
        "rag_ready": chunks_loaded > 0,
        "chunks_loaded": chunks_loaded,
        "bandit_ready": True,
        "features": ["RAG", "Thompson Sampling Bandit", "WebSocket Adaptation"]
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint with RAG context"""
    start_time = time.time()
    
    try:
        if len(rag.chunks) == 0:
            raise HTTPException(
                status_code=503, 
                detail="RAG not initialized."
            )
        
        # RAG retrieval (same as Week 2)
        rag_context = await rag.build_rag_context(request.question)
        
        if not rag_context["is_on_topic"]:
            elapsed_ms = (time.time() - start_time) * 1000
            return ChatResponse(
                answer=rag_context.get("error", "Outside scope."),
                is_on_topic=False,
                sources=0,
                context_used=False,
                latency_ms=elapsed_ms,
                mock=True
            )
        
        # Generate answer (same as Week 2)
        question_lower = request.question.lower()
        
        if any(kw in question_lower for kw in ["structure", "helix", "nucleotide"]):
            base_answer = MOCK_RESPONSES.get("structure")
        elif any(kw in question_lower for kw in ["replicate", "replication"]):
            base_answer = MOCK_RESPONSES.get("replication")
        elif any(kw in question_lower for kw in ["transcrib", "rna"]):
            base_answer = MOCK_RESPONSES.get("transcription")
        elif any(kw in question_lower for kw in ["translat", "protein"]):
            base_answer = MOCK_RESPONSES.get("translation")
        elif any(kw in question_lower for kw in ["mutant", "mutation"]):
            base_answer = MOCK_RESPONSES.get("mutation")
        else:
            base_answer = MOCK_RESPONSES.get("default")
        
        chunks = rag_context.get("chunks", [])
        context_used = len(chunks) > 0
        
        if context_used:
            answer = base_answer + "\n\n**Sources from curriculum:**\n"
            for i, chunk in enumerate(chunks[:2], 1):
                answer += f"\n{i}. {chunk['topic']} (Relevance: {chunk['similarity']:.1%})"
        else:
            answer = base_answer
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return ChatResponse(
            answer=answer,
            is_on_topic=True,
            sources=len(chunks),
            context_used=context_used,
            latency_ms=elapsed_ms,
            mock=USE_MOCK_LLM
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# WEBSOCKET ENDPOINT (New in Week 3)
# ============================================================

@app.websocket("/ws/adapt/{user_id}/{session_id}")
async def websocket_adapt(websocket: WebSocket, user_id: str, session_id: str):
    """
    WebSocket endpoint for real-time personalization.
    
    Flow:
    1. Client sends interaction event (question result)
    2. Server updates user state via bandit
    3. Server sends back personalization recommendation
    4. Repeat
    """
    await websocket.accept()
    logger.info(f"✅ WebSocket connected: user={user_id}, session={session_id}")
    
    try:
        # Get user state
        user_state = get_user_state(user_id)
        
        while True:
            # Receive interaction event
            data = await websocket.receive_text()
            event = json.loads(data)
            
            # Extract interaction details
            question = event.get("question", "")
            correct = event.get("correct", False)
            response_time_ms = event.get("response_time_ms", 3000)
            topic = event.get("topic", "DNA Structure")
            difficulty = event.get("difficulty", 1)
            
            # Update user state
            user_state.update_from_interaction(
                correct=correct,
                response_time_ms=response_time_ms,
                difficulty=difficulty,
                topic=topic,
            )
            
            # Get current state
            state_vector = user_state.get_state()
            
            # Bandit makes decision
            action = bandit.select_action(state_vector)
            action_info = ACTIONS[action]
            
            # Update bandit (reward: 1 if correct, 0 if incorrect)
            reward = 1.0 if correct else 0.0
            bandit.update(action, reward)
            
            # Build response
            if action < 3:
                recommended_difficulty = action
                recommended_topic = user_state.current_topic
            else:
                recommended_difficulty = user_state.current_difficulty
                recommended_topic = action_info.get("topic", "DNA Structure")
            
            adaptation_response = AdaptationResponse(
                user_id=user_id,
                action_id=action,
                action_name=action_info["name"],
                action_description=action_info["description"],
                recommended_difficulty=recommended_difficulty,
                recommended_topic=recommended_topic,
                user_state=user_state.to_dict(),
                timestamp=datetime.now().isoformat()
            )
            
            # Send back recommendation
            await websocket.send_json(adaptation_response.dict())
            
            logger.info(
                f"Adaptation: user={user_id}, action={action_info['name']}, "
                f"correct={correct}, latency=real-time"
            )
    
    except WebSocketDisconnect:
        logger.info(f"❌ WebSocket disconnected: user={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011)
        except:
            pass

# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "EduAR-AI Engineer - Week 3",
        "version": "0.3.0",
        "features": [
            "RAG retrieval (Week 2)",
            "Contextual bandit (Thompson sampling)",
            "Real-time WebSocket adaptation",
            "Pilot study support",
        ],
        "endpoints": {
            "health": "/health",
            "chat": "/chat (POST)",
            "adapt": "/ws/adapt/{user_id}/{session_id} (WebSocket)",
            "docs": "/docs"
        }
    }

# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():
    """Log startup information"""
    logger.info("=" * 70)
    logger.info("🚀 WEEK 3: RAG + CONTEXTUAL BANDIT AI SERVICE")
    logger.info("=" * 70)
    chunks_loaded = len(rag.chunks) if rag.chunks else 0
    logger.info(f"RAG ready: {chunks_loaded} chunks")
    logger.info(f"Bandit ready: Thompson Sampling (8 actions)")
    logger.info(f"API: http://{API_HOST}:{API_PORT}")
    logger.info("=" * 70 + "\n")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
