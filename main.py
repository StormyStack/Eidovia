#!/usr/bin/env python3
"""
Week 2 FastAPI: RAG Integration + Context-Aware Chat

Features:
- Topic detection (on-topic/off-topic)
- RAG retrieval from DNA curriculum
- Context-aware mock LLM responses
- Real embeddings (sentence-transformers)
- JSON-based chunk storage (no database needed)
"""

import logging
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config_week2 import (
    API_HOST,
    API_PORT,
    USE_MOCK_LLM,
    MOCK_RESPONSES,
)
from rag_week2 import get_rag

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-service")

# Pydantic models
class ChatRequest(BaseModel):
    question: str
    session_id: str = None

class ChatResponse(BaseModel):
    answer: str
    is_on_topic: bool
    sources: int
    context_used: bool
    latency_ms: float
    mock: bool = True

# Create FastAPI app
app = FastAPI(
    title="EduAR-AI Engineer - Week 2",
    description="AI tutor with RAG pipeline and context-aware responses",
    version="0.2.0"
)

# Get RAG instance
rag = get_rag()

# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint"""
    chunks_loaded = len(rag.chunks) if rag.chunks else 0
    
    return {
        "status": "healthy",
        "service": "ai-service",
        "version": "0.2.0",
        "rag_ready": chunks_loaded > 0,
        "chunks_loaded": chunks_loaded,
        "embedding_model": "all-MiniLM-L6-v2"
    }

# Chat endpoint with RAG
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with RAG context and context-aware responses.
    
    Week 2: Uses embeddings-based retrieval + mock LLM
    Week 3: Will integrate real Phi-3-Mini LLM
    """
    start_time = time.time()
    
    try:
        if len(rag.chunks) == 0:
            raise HTTPException(
                status_code=503, 
                detail="RAG not initialized. Run ingest_curriculum_week2.py first."
            )
        
        logger.info(f"Processing: {request.question[:80]}...")
        
        # Step 1: Build RAG context
        rag_context = await rag.build_rag_context(request.question)
        
        # Step 2: Check if on-topic
        if not rag_context["is_on_topic"]:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Off-topic. Similarity: {rag_context['topic_similarity']:.3f}")
            
            return ChatResponse(
                answer=rag_context.get("error", "This question is outside our scope."),
                is_on_topic=False,
                sources=0,
                context_used=False,
                latency_ms=elapsed_ms,
                mock=True
            )
        
        # Step 3: Generate answer
        question_lower = request.question.lower()
        
        # Match keywords to mock responses
        if any(kw in question_lower for kw in ["structure", "helix", "nucleotide", "base pair"]):
            base_answer = MOCK_RESPONSES.get("structure")
        elif any(kw in question_lower for kw in ["replicate", "replication", "copy"]):
            base_answer = MOCK_RESPONSES.get("replication")
        elif any(kw in question_lower for kw in ["transcrib", "rna", "mrna"]):
            base_answer = MOCK_RESPONSES.get("transcription")
        elif any(kw in question_lower for kw in ["translat", "protein", "ribosom"]):
            base_answer = MOCK_RESPONSES.get("translation")
        elif any(kw in question_lower for kw in ["mutant", "mutation", "change"]):
            base_answer = MOCK_RESPONSES.get("mutation")
        else:
            base_answer = MOCK_RESPONSES.get("default")
        
        # Step 4: Enhance with RAG context
        chunks = rag_context.get("chunks", [])
        context_used = len(chunks) > 0
        
        if context_used:
            # Add context source information
            answer = base_answer + "\n\n**Sources from curriculum:**\n"
            for i, chunk in enumerate(chunks[:2], 1):  # Use top 2 sources
                answer += f"\n{i}. {chunk['topic']} (Relevance: {chunk['similarity']:.1%})"
        else:
            answer = base_answer
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        logger.info(f"Answer generated. Sources: {len(chunks)}, Latency: {elapsed_ms:.1f}ms")
        
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

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "EduAR-AI Engineer - Week 2",
        "version": "0.2.0",
        "features": [
            "Topic detection (embedding-based)",
            "RAG retrieval from DNA curriculum",
            "Context-aware responses",
            "Mock LLM (real LLM in Week 3)"
        ],
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "docs": "/docs"
        }
    }

# Startup message
@app.on_event("startup")
async def startup():
    """Log startup information"""
    logger.info("=" * 60)
    logger.info("🚀 WEEK 2: RAG + CONTEXT-AWARE AI SERVICE STARTED")
    logger.info("=" * 60)
    chunks_loaded = len(rag.chunks) if rag.chunks else 0
    logger.info(f"Chunks loaded: {chunks_loaded}")
    logger.info(f"Embedding model: all-MiniLM-L6-v2")
    logger.info(f"API: http://{API_HOST}:{API_PORT}")
    logger.info("=" * 60 + "\n")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
