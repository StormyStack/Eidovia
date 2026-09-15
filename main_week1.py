import logging
import json
from fastapi import FastAPI
from pydantic import BaseModel

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
    latency_ms: float
    mock: bool = False

# Create FastAPI app
app = FastAPI(
    title="EduAR-AI Engineer Service",
    description="AI tutor with RAG and real-time adaptation",
    version="0.1.0"
)

# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ai-service",
        "version": "0.1.0"
    }

# Chat endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint with mock responses"""
    import time
    start_time = time.time()
    
    # Simple topic check
    question_lower = request.question.lower()
    dna_keywords = ["dna", "gene", "protein", "replication", "base", "nucleotide", "helix", "chromosome"]
    
    is_on_topic = any(kw in question_lower for kw in dna_keywords)
    
    if is_on_topic:
        answer = "This is a mock response about DNA biology. In Week 2, real LLM will answer this."
    else:
        answer = "This question is outside the scope of our DNA biology module."
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    return ChatResponse(
        answer=answer,
        is_on_topic=is_on_topic,
        sources=0,
        latency_ms=elapsed_ms,
        mock=True
    )

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "EduAR-AI Engineer",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "docs": "/docs"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")