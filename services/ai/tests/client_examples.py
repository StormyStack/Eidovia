"""
API Client Examples for EduAR-AI Service
Demonstrates how to interact with Chat and WebSocket endpoints.
"""

import asyncio
import json
import httpx
import websockets
from typing import Optional
from datetime import datetime

# ============================================================
# REST API CLIENT
# ============================================================

class ChatClient:
    """REST API client for chat endpoint."""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        """Initialize client."""
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def health_check(self) -> dict:
        """
        Check service health.
        
        Returns:
            Health status dictionary
        """
        response = await self.client.get(f"{self.base_url}/health")
        return response.json()
    
    async def chat(
        self,
        question: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        module_id: Optional[str] = None
    ) -> dict:
        """
        Send chat message and get response.
        
        Args:
            question: User question
            user_id: Optional user identifier
            session_id: Optional session identifier
            module_id: Optional module/topic identifier
            
        Returns:
            Chat response with answer and metadata
        """
        payload = {"question": question}
        if user_id:
            payload["user_id"] = user_id
        if session_id:
            payload["session_id"] = session_id
        if module_id:
            payload["module_id"] = module_id
        
        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json=payload
        )
        
        return response.json()


# ============================================================
# WEBSOCKET CLIENT
# ============================================================

class AdaptationClient:
    """WebSocket client for real-time adaptation."""
    
    def __init__(self, base_url: str = "ws://localhost:8001"):
        """Initialize client."""
        self.base_url = base_url
        self.ws = None
    
    async def connect(self, session_id: str):
        """
        Connect to WebSocket.
        
        Args:
            session_id: Session identifier
        """
        uri = f"{self.base_url}/ws/adapt/{session_id}"
        self.ws = await websockets.connect(uri)
    
    async def disconnect(self):
        """Disconnect from WebSocket."""
        if self.ws:
            await self.ws.close()
    
    async def send_interaction(
        self,
        question: str,
        correct: bool,
        response_time_ms: float,
        difficulty: int = 1
    ) -> dict:
        """
        Send interaction event and receive adaptation.
        
        Args:
            question: Question asked
            correct: Whether answer was correct
            response_time_ms: Time to answer (milliseconds)
            difficulty: Question difficulty (1-3)
            
        Returns:
            Adaptation response with recommended action
        """
        event = {
            "question": question,
            "correct": correct,
            "response_time_ms": response_time_ms,
            "difficulty": difficulty
        }
        
        await self.ws.send(json.dumps(event))
        response_text = await self.ws.recv()
        return json.loads(response_text)


# ============================================================
# EXAMPLE USAGE
# ============================================================

async def example_chat_client():
    """Example: Using chat REST API."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Chat REST API")
    print("=" * 70)
    
    client = ChatClient()
    
    try:
        # Check health
        health = await client.health_check()
        print(f"\n✅ Health: {health['status']}")
        print(f"   Database: {health['database']}")
        print(f"   RAG Ready: {health['rag_ready']}")
        
        # Chat on-topic
        print("\n📝 Asking on-topic question...")
        response = await client.chat(
            question="What is DNA structure?",
            user_id="user-123"
        )
        
        print(f"\n✅ Response:")
        print(f"   On-topic: {response['is_on_topic']}")
        print(f"   Similarity: {response['max_similarity']:.3f}")
        print(f"   Latency: {response['latency_ms']:.1f}ms")
        print(f"   Answer: {response['answer'][:100]}...")
        
        # Chat off-topic
        print("\n📝 Asking off-topic question...")
        response = await client.chat(
            question="What is the capital of France?",
            user_id="user-123"
        )
        
        print(f"\n❌ Response:")
        print(f"   On-topic: {response['is_on_topic']}")
        print(f"   Answer: {response['answer']}")
        
    finally:
        await client.close()


async def example_websocket_client():
    """Example: Using WebSocket adaptation API."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: WebSocket Adaptation")
    print("=" * 70)
    
    client = AdaptationClient()
    
    try:
        # Connect
        session_id = "session-456"
        print(f"\n🔗 Connecting to session: {session_id}")
        await client.connect(session_id)
        
        # Send interactions
        interactions = [
            {"q": "What causes mutations?", "correct": True, "time": 2500},
            {"q": "Define transcription", "correct": False, "time": 5000},
            {"q": "What is the genetic code?", "correct": True, "time": 1800},
        ]
        
        for i, interaction in enumerate(interactions, 1):
            print(f"\n📤 Interaction {i}:")
            print(f"   Question: {interaction['q']}")
            print(f"   Correct: {interaction['correct']}")
            print(f"   Response Time: {interaction['time']}ms")
            
            response = await client.send_interaction(
                question=interaction['q'],
                correct=interaction['correct'],
                response_time_ms=interaction['time'],
                difficulty=2
            )
            
            print(f"\n📥 Adaptation:")
            print(f"   Action: {response['action_name']}")
            print(f"   Reward: {response['reward']:.2f}")
            print(f"   Timestamp: {response['timestamp']}")
        
    finally:
        await client.disconnect()


async def example_concurrent_chats():
    """Example: Concurrent chat requests."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Concurrent Requests (Load Test)")
    print("=" * 70)
    
    client = ChatClient()
    
    try:
        questions = [
            "What is DNA replication?",
            "How does transcription work?",
            "What are mutations?",
            "Define the genetic code",
            "How does translation occur?"
        ]
        
        print(f"\n🚀 Sending {len(questions)} concurrent requests...")
        
        tasks = [
            client.chat(question=q, user_id=f"user-{i}")
            for i, q in enumerate(questions)
        ]
        
        start_time = datetime.utcnow()
        responses = await asyncio.gather(*tasks)
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        print(f"\n✅ Completed in {elapsed:.2f}s")
        print(f"   Requests: {len(responses)}")
        print(f"   Average latency: {sum(r['latency_ms'] for r in responses) / len(responses):.1f}ms")
        print(f"   On-topic: {sum(1 for r in responses if r['is_on_topic'])}/{len(responses)}")
        
    finally:
        await client.close()


async def main():
    """Run all examples."""
    print("\n" + "🎓 " * 35)
    print("EduAR-AI Service - API Client Examples")
    print("🎓 " * 35)
    
    try:
        # Run examples
        await example_chat_client()
        await asyncio.sleep(1)
        
        await example_websocket_client()
        await asyncio.sleep(1)
        
        await example_concurrent_chats()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure the service is running:")
        print("  python main_service.py")


if __name__ == "__main__":
    asyncio.run(main())
