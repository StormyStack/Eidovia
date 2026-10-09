import asyncio
import httpx

async def test_logout():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Login
        res = await client.post("/api/auth/login", json={"username": "testuser_1_9775", "password": "password123"})
        if res.status_code != 200:
            print(f"Login failed: {res.status_code}")
            return
        token = res.json()["token"]
        print(f"Logged in, token: {token[:20]}...")
        
        # Logout
        res = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        print(f"Logout response: {res.status_code} - {res.text}")

if __name__ == "__main__":
    asyncio.run(test_logout())
