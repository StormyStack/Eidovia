import logging
import os
import time
from typing import Any, List
import httpx
from sqlalchemy import text
from db import db
from redis_client import get_redis
from schemas import SystemAnnouncementCreate

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", os.getenv("LLM_BASE_URL", "http://ollama:11434")).rstrip("/")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "phi4-mini")


class SystemService:
    @staticmethod
    async def get_system_health() -> dict[str, Any]:
        health: dict[str, Any] = {
            "status": "healthy",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "database": {"connected": False},
            "redis": {"connected": False},
            "ai_service": {"connected": False},
        }

        # 1. Database check
        try:
            async with db.get_session() as session:
                t0 = time.perf_counter()
                res = await session.execute(text("SELECT version(), pg_database_size(current_database()) as dbsize"))
                row = res.first()
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                health["database"] = {
                    "connected": True,
                    "latency_ms": latency_ms,
                    "version": row[0].split()[0] + " " + row[0].split()[1] if row else "PostgreSQL",
                    "db_size_bytes": row.dbsize if row else 0,
                }
        except Exception as e:
            health["status"] = "degraded"
            health["database"] = {"connected": False, "error": str(e)}

        # 2. Redis check
        try:
            r = await get_redis()
            t0 = time.perf_counter()
            pong = await r.ping()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            dbsize = await r.dbsize()
            raw_queue_len = await r.llen("raw_audit_logs")
            info_mem = await r.info("memory")
            health["redis"] = {
                "connected": pong,
                "latency_ms": latency_ms,
                "total_keys": dbsize,
                "audit_queue_backlog": raw_queue_len,
                "used_memory_human": info_mem.get("used_memory_human", "N/A"),
            }
        except Exception as e:
            health["status"] = "degraded"
            health["redis"] = {"connected": False, "error": str(e)}

        # 3. Ollama AI check
        try:
            t0 = time.perf_counter()
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{OLLAMA_URL}/api/version")
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                if res.status_code == 200:
                    health["ai_service"] = {
                        "connected": True,
                        "latency_ms": latency_ms,
                        "engine": "Ollama",
                        "active_model": OLLAMA_MODEL,
                        "version": res.json().get("version", "unknown"),
                    }
                else:
                    health["ai_service"] = {"connected": False, "status_code": res.status_code}
        except Exception as e:
            health["status"] = "degraded"
            health["ai_service"] = {"connected": False, "error": str(e)}

        return health

    @staticmethod
    async def flush_cache() -> dict[str, Any]:
        """Purges Redis hot AI answers cache."""
        r = await get_redis()
        keys = []
        async for key in r.scan_iter("hot_msg:*"):
            keys.append(key)
        deleted = 0
        if keys:
            deleted = await r.delete(*keys)
        return {"status": "cache_flushed", "deleted_keys": deleted}

    @staticmethod
    async def create_announcement(data: SystemAnnouncementCreate) -> dict[str, Any]:
        async with db.get_session() as session:
            res = await session.execute(
                text("""
                    INSERT INTO system_announcements (title, message, level, is_active)
                    VALUES (:title, :message, :level, TRUE)
                    RETURNING announcement_id, title, message, level, is_active, created_at
                """),
                {"title": data.title, "message": data.message, "level": data.level}
            )
            row = res.first()
            await session.commit()
            return {
                "announcement_id": str(row.announcement_id),
                "title": row.title,
                "message": row.message,
                "level": row.level,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    @staticmethod
    async def list_announcements() -> List[dict[str, Any]]:
        async with db.get_session() as session:
            res = await session.execute(
                text("SELECT announcement_id, title, message, level, is_active, created_at FROM system_announcements ORDER BY created_at DESC LIMIT 20")
            )
            announcements = []
            for row in res.all():
                announcements.append({
                    "announcement_id": str(row.announcement_id),
                    "title": row.title,
                    "message": row.message,
                    "level": row.level,
                    "is_active": row.is_active,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            return announcements
