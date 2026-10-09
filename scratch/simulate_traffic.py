import asyncio
import httpx
import random
import uuid

BASE_URL = "http://localhost:8000"

async def simulate_user(user_index: int):
    username = f"testuser_{user_index}_{uuid.uuid4().hex[:4]}"
    password = "password123"
    
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        print(f"[{username}] Registering...")
        res = await client.post("/api/auth/register", json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "language": "en"
        })
        
        if res.status_code != 201:
            print(f"[{username}] Register failed: {res.text}")
            return
            
        token = res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        # Send a few chat messages
        for i in range(3):
            print(f"[{username}] Sending message {i+1}...")
            res = await client.post("/api/chat", json={
                "question": f"Hello, this is message {i+1} from {username}!",
                "session_id": str(uuid.uuid4())
            }, headers=headers)
            
            if res.status_code == 200:
                print(f"[{username}] Reply: {res.json().get('answer')}")
            else:
                print(f"[{username}] Chat error: {res.status_code}")
                
            await asyncio.sleep(random.uniform(2.0, 5.0))
            
        # Log out
        print(f"[{username}] Logging out...")
        await client.post("/api/auth/logout", headers=headers)
        print(f"[{username}] Done.")

async def main():
    print("Starting traffic simulation. Open the Admin Dashboard to watch!")
    
    # Run 3 users concurrently
    tasks = [simulate_user(i) for i in range(1, 4)]
    await asyncio.gather(*tasks)
    
if __name__ == "__main__":
    asyncio.run(main())
