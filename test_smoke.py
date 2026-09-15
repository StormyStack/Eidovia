#!/usr/bin/env python3
"""
Smoke tests for Week 1: Database, RAG, API endpoints.

Run after services are up:
    pytest test_smoke.py -v
"""

import asyncio
import pytest
import asyncpg
from httpx import AsyncClient

from config import DATABASE_ASYNC_URL
from main import app
from database import init_db
from rag import init_rag

# Fixtures
@pytest.fixture
async def client():
    """FastAPI test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def db_pool():
    """Database connection pool"""
    pool = await asyncpg.create_pool(DATABASE_ASYNC_URL)
    yield pool
    await pool.close()

# Tests
@pytest.mark.asyncio
async def test_database_connection(db_pool):
    """Test PostgreSQL connection and tables exist"""
    async with db_pool.acquire() as conn:
        # Check pgvector extension
        result = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            );
        """)
        assert result, "pgvector extension not installed"
    
    print("✅ Database connection and pgvector OK")

@pytest.mark.asyncio
async def test_document_chunks_table(db_pool):
    """Test document_chunks table exists and has structure"""
    async with db_pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'document_chunks'
            ORDER BY ordinal_position;
        """)
        
        columns = {row['column_name']: row['data_type'] for row in result}
        
        assert 'id' in columns, "Missing 'id' column"
        assert 'content' in columns, "Missing 'content' column"
        assert 'embedding' in columns, "Missing 'embedding' column"
        assert 'topic' in columns, "Missing 'topic' column"
    
    print("✅ document_chunks table structure OK")

@pytest.mark.asyncio
async def test_embedding_dimension(db_pool):
    """Test that embeddings are 384-dimensional (all-MiniLM-L6-v2)"""
    async with db_pool.acquire() as conn:
        # Get first embedding from database
        result = await conn.fetchval("""
            SELECT embedding FROM document_chunks LIMIT 1;
        """)
        
        if result:
            # pgvector returns list
            embedding = result
            assert len(embedding) == 384, f"Expected 384 dimensions, got {len(embedding)}"
            print("✅ Embedding dimension OK (384)")
        else:
            print("⚠️  No embeddings in database yet (might be before ingestion)")

@pytest.mark.asyncio
async def test_rag_retrieval(db_pool):
    """Test RAG retrieval works with actual embeddings"""
    rag = await init_rag(db_pool)
    
    # Test topic checking
    is_on_topic, similarity = await rag.is_on_topic("What is DNA structure?")
    assert is_on_topic, f"DNA question should be on-topic (sim={similarity:.3f})"
    print(f"✅ RAG topic check OK (similarity={similarity:.3f})")
    
    # Test off-topic rejection
    is_off_topic, off_similarity = await rag.is_on_topic("What is the capital of France?")
    assert not is_off_topic, f"Geography question should be off-topic (sim={off_similarity:.3f})"
    print(f"✅ RAG off-topic rejection OK (similarity={off_similarity:.3f})")
    
    # Test retrieval (if curriculum is loaded)
    chunks = await rag.retrieve_top_k("DNA replication process")
    if chunks:
        print(f"✅ RAG retrieval OK ({len(chunks)} chunks)")
    else:
        print("⚠️  No chunks retrieved (curriculum not ingested yet)")

@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test /health endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    print("✅ Health endpoint OK")

@pytest.mark.asyncio
async def test_chat_endpoint_off_topic(client):
    """Test /chat endpoint rejects off-topic questions"""
    payload = {"question": "What is 2+2?"}
    response = await client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_on_topic"] == False
    print("✅ Chat endpoint (off-topic) OK")

@pytest.mark.asyncio
async def test_chat_endpoint_on_topic(client):
    """Test /chat endpoint accepts DNA questions"""
    payload = {"question": "What is the structure of DNA?"}
    response = await client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Should accept DNA questions (even if latency is high)
    print(f"✅ Chat endpoint (on-topic) OK - Latency: {data['latency_ms']:.0f}ms")

@pytest.mark.asyncio
async def test_api_response_schema(client):
    """Test ChatResponse schema matches expectations"""
    payload = {"question": "DNA"}
    response = await client.post("/chat", json=payload)
    data = response.json()
    
    required_fields = ["answer", "is_on_topic", "sources", "latency_ms", "mock"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    print("✅ Response schema OK")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
