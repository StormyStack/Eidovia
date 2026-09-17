#!/usr/bin/env python3
"""
FastAPI Adaptive AI Tutor - PostgreSQL Backend
Week 4 Integration: RAG + Contextual Bandit + Database Logging
FIXED: Load embedding model once at startup
"""

import logging
import asyncio
import numpy as np
from fastapi import FastAPI, WebSocket, HTTPException
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4, UUID
import json

# Import our modules
from models_postgres import User, Session, Event, DocumentChunk, AiDecisionLog, RlEpisode
from database_postgres import Database
from rag_postgres import RAGRetriever
from bandit_postgres import ContextualBandit
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-service-postgres")

# ============================================================
# FASTAPI APP SETUP
# ============================================================

app = FastAPI(
    title="Adaptive AI Tutor - PostgreSQL Backend",
    description="Week 4: RAG + Contextual Bandit with PostgreSQL logging",
    version="0.4.0"
)

# Global instances
db = Database()
rag = None
bandit = None
embedding_model = None  # Load once at startup

# ============================================================
# PYDANTIC MODELS
# ============================================================

class ChatRequest(BaseModel):
    question: str
    user_id: str = None
    session_id: str = None

class ChatResponse(BaseModel):
    answer: str
    is_on_topic: bool
    topic_similarity: float
    retrieved_chunks: int
    latency_ms: float
    decision_id: str = None

class AdaptationRequest(BaseModel):
    question: str
    correct: bool
    response_time_ms: float
    topic: str
    difficulty: int

class AdaptationResponse(BaseModel):
    user_id: str
    action_id: int
    action_name: str
    recommended_difficulty: int
    recommended_topic: str
    reward: float
    latency_ms: float

# ============================================================
# LIFECYCLE EVENTS
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database and load models on startup"""
    global rag, bandit, embedding_model
    
    logger.info("=" * 70)
    logger.info("🚀 WEEK 4: ADAPTIVE AI TUTOR - POSTGRESQL BACKEND")
    logger.info("=" * 70)
    
    try:
        # Load embedding model ONCE at startup
        logger.info("Loading embedding model...")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("✅ Embedding model loaded: all-MiniLM-L6-v2")
        
        # Connect to database
        await db.connect()
        logger.info("✅ Database connected: PostgreSQL 16")
        
        # Initialize RAG
        rag = RAGRetriever(db=db, threshold=0.40, top_k=3)
        chunks_loaded = await rag.load_chunks()
        logger.info(f"✅ RAG: {len(rag.chunks)} chunks loaded from database")
        
        # Initialize Bandit
        bandit = ContextualBandit(db=db, state_dim=8, num_actions=8)
        logger.info("✅ Bandit: Thompson Sampling initialized (8 actions)")
        
        logger.info("=" * 70)
        logger.info("API: http://127.0.0.1:8001")
        logger.info("=" * 70)
    
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await db.disconnect()
    logger.info("Database disconnected")

# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "service": "ai-service-postgres",
        "version": "0.4.0",
        "database": "postgresql",
        "rag_ready": len(rag.chunks) > 0 if rag else False,
        "bandit_ready": bandit is not None,
        "chunks_loaded": len(rag.chunks) if rag else 0,
        "embedding_model": "all-MiniLM-L6-v2" if embedding_model else None,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint with RAG + decision logging"""
    
    if not rag:
        raise HTTPException(status_code=503, detail="RAG not initialized")
    if not embedding_model:
        raise HTTPException(status_code=503, detail="Embedding model not initialized")
    
    start_time = datetime.utcnow()
    
    try:
        # Get or create user/session
        user_id = request.user_id or str(uuid4())
        session_id = request.session_id or str(uuid4())
        
        # Generate query embedding using global model (FAST!)
        query_embedding = embedding_model.encode([request.question], convert_to_numpy=True)[0]
        
        # Build RAG context
        rag_context = await rag.build_context(request.question, query_embedding)
        
        # Generate response
        if rag_context["is_on_topic"]:
            llm_response = f"Based on our curriculum: {rag_context['context']}\n\nAnswer: This topic covers DNA biology concepts including structure, replication, and molecular mechanisms."
        else:
            llm_response = rag_context.get("error", "This question is outside our scope.")
        
        # Calculate latency
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Log decision to database
        decision_data = {
            'user_id': UUID(user_id),
            'session_id': UUID(session_id),
            'question': request.question,
            'is_on_topic': rag_context["is_on_topic"],
            'topic_similarity': rag_context["topic_similarity"],
            'retrieved_chunks': len(rag_context["chunks"]),
            'llm_response': llm_response,
            'latency_ms': latency_ms,
            'action_id': None,
            'action_name': None,
            'reward': 0.0
        }
        
        decision_id = await db.log_decision(decision_data)
        
        logger.info(f"Chat: {request.question[:50]}... | On-topic: {rag_context['is_on_topic']} | Latency: {latency_ms:.1f}ms")
        
        return ChatResponse(
            answer=llm_response,
            is_on_topic=rag_context["is_on_topic"],
            topic_similarity=rag_context["topic_similarity"],
            retrieved_chunks=len(rag_context["chunks"]),
            latency_ms=latency_ms,
            decision_id=str(decision_id) if decision_id else None
        )
    
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# WEBSOCKET ADAPTATION
# ============================================================

@app.websocket("/ws/adapt/{user_id}/{session_id}")
async def websocket_adapt(websocket: WebSocket, user_id: str, session_id: str):
    """Real-time adaptation via WebSocket"""
    
    await websocket.accept()
    logger.info(f"✅ WebSocket connected: user={user_id}, session={session_id}")
    
    try:
        while True:
            # Receive interaction event
            data = await websocket.receive_text()
            event = json.loads(data)
            
            # Extract event data
            question = event.get("question", "")
            correct = event.get("correct", False)
            response_time_ms = event.get("response_time_ms", 3000)
            topic = event.get("topic", "DNA Structure")
            difficulty = event.get("difficulty", 1)
            
            # Generate state vector (8D)
            state_vector = [
                1.0 if correct else 0.0,  # accuracy
                min(response_time_ms / 5000, 1.0),  # response_time_norm
                float(difficulty) / 3,  # difficulty_level
                0.5,  # topic_match
                0.5,  # engagement
                0.01,  # question_count_norm
                0.0 if correct else 1.0,  # error_rate
                min(response_time_ms / 10000, 1.0)  # time_spent_norm
            ]
            
            # Select action using Thompson Sampling
            action_id = bandit.select_action(np.array(state_vector))
            action_name = bandit.action_names[action_id]
            
            # Map action to recommended settings
            if action_id == 0:
                rec_difficulty = 1
            elif action_id == 1:
                rec_difficulty = 2
            else:
                rec_difficulty = 3
            
            rec_topic = ["DNA Structure", "DNA Replication", "Transcription", "Translation", "Mutations"][
                (action_id - 3) % 5
            ] if action_id >= 3 else topic
            
            # Calculate reward
            reward = 1.0 if correct else 0.0
            
            # Update bandit
            await bandit.update(action_id, reward)
            
            # Log decision
            latency_ms = 50  # WebSocket processing time
            decision_id = await bandit.log_decision(
                user_id=UUID(user_id),
                session_id=UUID(session_id),
                question=question,
                is_on_topic=True,
                topic_similarity=0.7,
                retrieved_chunks=3,
                llm_response="",
                latency_ms=latency_ms,
                action_id=action_id,
                recommended_difficulty=rec_difficulty,
                recommended_topic=rec_topic,
                reward=reward
            )
            
            # Log episode
            episode_id = await bandit.log_episode(
                user_id=UUID(user_id),
                session_id=UUID(session_id),
                state_vector=state_vector,
                action_id=action_id,
                reward=reward,
                done=False
            )
            
            # Send response
            response = {
                "user_id": user_id,
                "action_id": action_id,
                "action_name": action_name,
                "recommended_difficulty": rec_difficulty,
                "recommended_topic": rec_topic,
                "reward": reward,
                "latency_ms": latency_ms,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await websocket.send_json(response)
            logger.info(f"Adaptation: user={user_id} | action={action_name} | reward={reward:.2f}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info(f"❌ WebSocket disconnected: user={user_id}")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)