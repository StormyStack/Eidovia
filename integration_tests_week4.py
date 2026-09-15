#!/usr/bin/env python3
"""
Week 4 Integration Tests
End-to-end testing of the complete adaptive learning system
"""

import asyncio
import json
import logging
import numpy as np
from datetime import datetime

import websockets
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration_tests")

class IntegrationTester:
    """Integration test suite for Week 3 system"""
    
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http://", "ws://")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "passed": 0,
            "failed": 0,
            "performance": {}
        }
    
    async def test_health_check(self):
        """Test 1: Health check endpoint"""
        logger.info("\n[Test 1] Health Check")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["rag_ready"] == True
                assert data["bandit_ready"] == True
                assert data["chunks_loaded"] == 10
            
            logger.info("✅ PASSED: Health check OK")
            self.results["tests"].append({"name": "health_check", "status": "PASSED"})
            self.results["passed"] += 1
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results["tests"].append({"name": "health_check", "status": "FAILED", "error": str(e)})
            self.results["failed"] += 1
            return False
    
    async def test_chat_on_topic(self):
        """Test 2: Chat endpoint with on-topic question"""
        logger.info("\n[Test 2] Chat - On-Topic Question")
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "question": "What is DNA structure?",
                    "user_id": "test_user_1",
                    "session_id": "test_session_1"
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
                
                self.results["performance"]["chat_on_topic_ms"] = data["latency_ms"]
            
            logger.info(f"✅ PASSED: On-topic chat (latency: {data['latency_ms']:.1f}ms)")
            self.results["tests"].append({"name": "chat_on_topic", "status": "PASSED"})
            self.results["passed"] += 1
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results["tests"].append({"name": "chat_on_topic", "status": "FAILED", "error": str(e)})
            self.results["failed"] += 1
            return False
    
    async def test_chat_off_topic(self):
        """Test 3: Chat endpoint with off-topic question"""
        logger.info("\n[Test 3] Chat - Off-Topic Question")
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "question": "What is the capital of France?",
                    "user_id": "test_user_2"
                }
                response = await client.post(
                    f"{self.base_url}/chat",
                    json=payload
                )
                assert response.status_code == 200
                data = response.json()
                assert data["is_on_topic"] == False
                assert "scope" in data["answer"].lower() or "outside" in data["answer"].lower()
            
            logger.info("✅ PASSED: Off-topic question rejected correctly")
            self.results["tests"].append({"name": "chat_off_topic", "status": "PASSED"})
            self.results["passed"] += 1
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results["tests"].append({"name": "chat_off_topic", "status": "FAILED", "error": str(e)})
            self.results["failed"] += 1
            return False
    
    async def test_websocket_adaptation(self):
        """Test 4: WebSocket real-time adaptation"""
        logger.info("\n[Test 4] WebSocket Adaptation")
        try:
            uri = f"{self.ws_url}/ws/adapt/test_user_3/test_session_3"
            async with websockets.connect(uri) as ws:
                # Send first interaction
                event_1 = {
                    "question": "What is DNA?",
                    "correct": True,
                    "response_time_ms": 3500,
                    "topic": "DNA Structure",
                    "difficulty": 1
                }
                await ws.send(json.dumps(event_1))
                response_1 = await ws.recv()
                data_1 = json.loads(response_1)
                
                assert "action_id" in data_1
                assert "recommended_difficulty" in data_1
                assert "user_state" in data_1
                latency_1 = 1  # Approximate latency
                
                # Send second interaction
                event_2 = {
                    "question": "How does replication work?",
                    "correct": False,
                    "response_time_ms": 4200,
                    "topic": "DNA Replication",
                    "difficulty": 2
                }
                await ws.send(json.dumps(event_2))
                response_2 = await ws.recv()
                data_2 = json.loads(response_2)
                
                # Verify state updated
                assert data_2["user_state"]["questions_answered"] == 2
                assert data_2["user_state"]["accuracy"] < 1.0  # One wrong answer
            
            logger.info("✅ PASSED: WebSocket adaptation working")
            self.results["tests"].append({"name": "websocket_adaptation", "status": "PASSED"})
            self.results["passed"] += 1
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results["tests"].append({"name": "websocket_adaptation", "status": "FAILED", "error": str(e)})
            self.results["failed"] += 1
            return False
    
    async def test_bandit_decisions(self):
        """Test 5: Bandit makes different decisions"""
        logger.info("\n[Test 5] Bandit Decision Diversity")
        try:
            actions = set()
            uri = f"{self.ws_url}/ws/adapt/test_user_4/test_session_4"
            
            async with websockets.connect(uri) as ws:
                for i in range(5):
                    event = {
                        "question": f"Question {i+1}",
                        "correct": i % 2 == 0,  # Alternate correct/incorrect
                        "response_time_ms": 3000 + i * 200,
                        "topic": ["DNA Structure", "DNA Replication", "Transcription", "Translation", "Mutations"][i % 5],
                        "difficulty": i % 3
                    }
                    await ws.send(json.dumps(event))
                    response = await ws.recv()
                    data = json.loads(response)
                    actions.add(data["action_id"])
            
            # Bandit should explore multiple actions
            assert len(actions) >= 2, f"Bandit should explore (got {len(actions)} unique actions)"
            
            logger.info(f"✅ PASSED: Bandit explored {len(actions)} different actions")
            self.results["tests"].append({"name": "bandit_diversity", "status": "PASSED"})
            self.results["passed"] += 1
            return True
        except Exception as e:
            logger.error(f"❌ FAILED: {e}")
            self.results["tests"].append({"name": "bandit_diversity", "status": "FAILED", "error": str(e)})
            self.results["failed"] += 1
            return False
    
    async def run_all_tests(self):
        """Run complete test suite"""
        logger.info("=" * 70)
        logger.info("🧪 WEEK 4: INTEGRATION TEST SUITE")
        logger.info("=" * 70)
        
        await self.test_health_check()
        await self.test_chat_on_topic()
        await self.test_chat_off_topic()
        await self.test_websocket_adaptation()
        await self.test_bandit_decisions()
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Passed: {self.results['passed']}")
        logger.info(f"Failed: {self.results['failed']}")
        logger.info(f"Total:  {self.results['passed'] + self.results['failed']}")
        logger.info("=" * 70 + "\n")
        
        # Save results
        with open("data/integration_test_results.json", 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Results saved to data/integration_test_results.json")
        
        return self.results["failed"] == 0

async def main():
    tester = IntegrationTester()
    success = await tester.run_all_tests()
    exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
