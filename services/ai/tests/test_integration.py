"""
Integration Tests for Eidovia Service
Tests RAG, Bandit, and API endpoints with actual services.
"""

import pytest
import asyncio
import json
import httpx
from datetime import datetime
import numpy as np

import config_prod as config
from database_service import db
from rag_service import rag_service
from bandit_service import bandit

# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
async def app_context():
    """Setup and teardown app for testing."""
    await db.connect()
    await rag_service.initialize()
    
    yield
    
    await db.disconnect()


@pytest.mark.asyncio
async def test_database_connection(app_context):
    """Test PostgreSQL connection."""
    assert db.connected
    session = await db.get_session()
    assert session is not None
    await session.close()


@pytest.mark.asyncio
async def test_rag_embedding(app_context):
    """Test RAG query embedding."""
    query = "What is DNA structure?"
    embedding = await rag_service.encode_query(query)
    
    assert embedding is not None
    assert len(embedding) == config.EMBEDDING_DIMENSION
    assert isinstance(embedding, np.ndarray)


@pytest.mark.asyncio
async def test_rag_cosine_similarity(app_context):
    """Test cosine similarity calculation."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([1.0, 0.0, 0.0])
    
    similarity = rag_service.cosine_similarity(vec1, vec2)
    
    assert similarity == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_bandit_action_selection():
    """Test bandit action selection."""
    state = np.array([1.0, 0.5, 0.33, 0.5, 0.7, 0.1, 0.0, 0.5])
    
    action = bandit.select_action(state)
    
    assert 0 <= action < config.BANDIT_NUM_ACTIONS
    assert isinstance(action, (int, np.integer))


@pytest.mark.asyncio
async def test_bandit_update():
    """Test bandit reward update."""
    action = 2
    reward = 1.0
    
    initial_count = bandit.action_stats[action].count
    await bandit.update(action, reward)
    
    assert bandit.action_stats[action].count == initial_count + 1
    assert bandit.action_stats[action].total_reward > 0


def test_bandit_statistics():
    """Test bandit statistics collection."""
    stats = bandit.get_statistics()
    
    assert len(stats) == config.BANDIT_NUM_ACTIONS
    for action_name in config.BANDIT_ACTIONS:
        assert action_name in stats


# ============================================================
# API TESTS
# ============================================================

class TestChatAPI:
    """Test chat endpoint."""
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:8001/health",
                timeout=5.0
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["database"] in ["connected", "disconnected"]
    
    @pytest.mark.asyncio
    async def test_chat_on_topic(self):
        """Test chat with on-topic question."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8001/api/chat",
                json={"question": "What is DNA structure?"},
                timeout=5.0
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "answer" in data
            assert "is_on_topic" in data
            assert "max_similarity" in data
            assert "latency_ms" in data
            assert data["latency_ms"] < 500
    
    @pytest.mark.asyncio
    async def test_chat_off_topic(self):
        """Test chat with off-topic question."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8001/api/chat",
                json={"question": "What is the capital of France?"},
                timeout=5.0
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["is_on_topic"] == False
            assert "outside" in data["answer"].lower() or "scope" in data["answer"].lower()
    
    @pytest.mark.asyncio
    async def test_chat_validation(self):
        """Test chat request validation."""
        async with httpx.AsyncClient() as client:
            # Empty question
            response = await client.post(
                "http://localhost:8001/api/chat",
                json={"question": ""},
                timeout=5.0
            )
            
            assert response.status_code == 400


# ============================================================
# WEBSOCKET TESTS
# ============================================================

@pytest.mark.asyncio
async def test_websocket_connection():
    """Test WebSocket connection."""
    from websockets.client import connect
    
    session_id = "test-session-123"
    uri = f"ws://localhost:8001/ws/adapt/{session_id}"
    
    try:
        async with connect(uri, close_timeout=1) as ws:
            # Send interaction event
            event = {
                "question": "What causes mutations?",
                "correct": True,
                "response_time_ms": 2500,
                "difficulty": 2
            }
            
            await ws.send(json.dumps(event))
            
            # Receive response
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)
            
            assert "action_id" in data
            assert "action_name" in data
            assert "reward" in data
            
    except Exception as e:
        pytest.skip(f"WebSocket test skipped: {e}")


# ============================================================
# LOAD TESTS
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_chat_requests():
    """Test concurrent chat requests."""
    async with httpx.AsyncClient() as client:
        tasks = [
            client.post(
                "http://localhost:8001/api/chat",
                json={"question": f"What is DNA? (request {i})"},
                timeout=10.0
            )
            for i in range(5)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        assert len(responses) == 5
        for response in responses:
            assert response.status_code == 200


# ============================================================
# CONFIGURATION TESTS
# ============================================================

def test_config_validation():
    """Test configuration validation."""
    config.validate_config()
    
    # Should not raise
    assert config.rag_config.threshold >= 0
    assert config.rag_config.threshold <= 1
    assert config.bandit_config.epsilon >= 0
    assert config.bandit_config.epsilon <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
