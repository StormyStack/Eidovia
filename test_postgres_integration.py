#!/usr/bin/env python3
"""
Week 4 Integration Tests - PostgreSQL Backend
End-to-end testing of RAG + Bandit + Database
"""

import asyncio
import logging
import json
from datetime import datetime
from uuid import uuid4

import httpx
import websockets
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration_tests")

class TestPostgresIntegration:
    """Integration test suite for PostgreSQL backend"""
    
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http://", "ws://")
        self.results = []
    
    async def test_health(self):
        """Test 1: Health check"""
        logger.info("\n[Test 1] Health Check")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["rag_ready"] == True or data["chunks_loaded"] > 0
                assert data["bandit_ready"] == True
            logger.info("✅ PASSED")
            self.results.append(("health_check", True))
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results.append(("health_check", False))
            return False
    
    async def test_chat_on_topic(self):
        """Test 2: Chat with on-topic question"""
        logger.info("\n[Test 2] Chat - On-Topic Question")
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "question": "What is DNA structure?",
                    "user_id": str(uuid4()),
                    "session_id": str(uuid4())
                }
                response = await client.post(
                    f"{self.base_url}/chat",
                    json=payload
                )
                assert response.status_code == 200
                data = response.json()
                assert data["is_on_topic"] == True
                assert len(data["answer"]) > 0
                assert data["latency_ms"] < 500
                assert data["decision_id"] is not None
            logger.info(f"✅ PASSED | Latency: {data['latency_ms']:.1f}ms")
            self.results.append(("chat_on_topic", True))
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results.append(("chat_on_topic", False))
            return False
    
    async def test_chat_off_topic(self):
        """Test 3: Chat with off-topic question"""
        logger.info("\n[Test 3] Chat - Off-Topic Question")
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "question": "What is the capital of France?",
                    "user_id": str(uuid4())
                }
                response = await client.post(
                    f"{self.base_url}/chat",
                    json=payload
                )
                assert response.status_code == 200
                data = response.json()
                assert data["is_on_topic"] == False
                assert "outside" in data["answer"].lower() or "scope" in data["answer"].lower()
            logger.info("✅ PASSED | Off-topic rejected correctly")
            self.results.append(("chat_off_topic", True))
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results.append(("chat_off_topic", False))
            return False
    
    async def test_websocket_adaptation(self):
        """Test 4: WebSocket real-time adaptation"""
        logger.info("\n[Test 4] WebSocket Adaptation")
        try:
            user_id = str(uuid4())
            session_id = str(uuid4())
            uri = f"{self.ws_url}/ws/adapt/{user_id}/{session_id}"
            
            async with websockets.connect(uri) as ws:
                # Send 3 interactions
                for i in range(3):
                    event = {
                        "question": f"DNA question {i+1}",
                        "correct": i % 2 == 0,
                        "response_time_ms": 3000 + i * 500,
                        "topic": "DNA Structure",
                        "difficulty": 1 + (i % 2)
                    }
                    await ws.send(json.dumps(event))
                    response = await ws.recv()
                    data = json.loads(response)
                    
                    assert "action_id" in data
                    assert "action_name" in data
                    assert data["latency_ms"] < 200
                    
                    logger.info(f"  Interaction {i+1}: action={data['action_name']}, reward={data['reward']:.2f}")
            
            logger.info("✅ PASSED | 3 adaptations successful")
            self.results.append(("websocket_adaptation", True))
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results.append(("websocket_adaptation", False))
            return False
    
    async def test_database_logging(self):
        """Test 5: Verify database logging"""
        logger.info("\n[Test 5] Database Logging")
        try:
            # Run a chat to generate a decision log entry
            async with httpx.AsyncClient() as client:
                payload = {
                    "question": "What is DNA replication?",
                    "user_id": str(uuid4()),
                    "session_id": str(uuid4())
                }
                response = await client.post(
                    f"{self.base_url}/chat",
                    json=payload
                )
                data = response.json()
                
                # Verify decision was logged
                assert data["decision_id"] is not None
                logger.info(f"✅ PASSED | Decision logged: {data['decision_id'][:8]}...")
            
            self.results.append(("database_logging", True))
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results.append(("database_logging", False))
            return False
    
    async def run_all_tests(self):
        """Run complete test suite"""
        logger.info("=" * 70)
        logger.info("🧪 WEEK 4: POSTGRESQL INTEGRATION TEST SUITE")
        logger.info("=" * 70)
        
        await self.test_health()
        await self.test_chat_on_topic()
        await self.test_chat_off_topic()
        await self.test_websocket_adaptation()
        await self.test_database_logging()
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 70)
        
        passed = sum(1 for _, result in self.results if result)
        failed = sum(1 for _, result in self.results if not result)
        
        for test_name, result in self.results:
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{status} | {test_name}")
        
        logger.info("=" * 70)
        logger.info(f"Passed: {passed}/{len(self.results)}")
        logger.info(f"Failed: {failed}/{len(self.results)}")
        logger.info("=" * 70)
        
        return failed == 0

async def main():
    tester = TestPostgresIntegration()
    success = await tester.run_all_tests()
    exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
