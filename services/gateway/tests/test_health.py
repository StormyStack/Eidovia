"""GET /health and database reachability."""

import asyncio

from app.db import DatabaseService


def test_health_reports_connected(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "gateway", "database": "connected"}


def test_ping_is_false_when_database_unreachable(gateway_env):
    async def _check():
        database = DatabaseService()
        await database.connect("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
        try:
            return await database.ping()
        finally:
            await database.disconnect()

    assert asyncio.run(_check()) is False
