import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:8001/ws/adapt/user_123/session_001") as ws:
        event = {
            "question": "What is DNA?",
            "correct": True,
            "response_time_ms": 3500,
            "topic": "DNA Structure",
            "difficulty": 1
        }
        await ws.send(json.dumps(event))
        response = await ws.recv()
        print(json.loads(response))

asyncio.run(test())