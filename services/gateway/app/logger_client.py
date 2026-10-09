import json
import logging
from datetime import datetime, timezone
import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool = None

async def get_redis():
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True
        )
    return _redis_pool

async def push_log_event(action: str, user_id: str, details: dict = None):
    """
    Pushes a raw log event to Redis for the logger service to process.
    """
    try:
        r = await get_redis()
        event = {
            "action": action,
            "user_id": user_id,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await r.rpush("raw_audit_logs", json.dumps(event))
    except Exception as e:
        logger.error(f"Failed to push log event to Redis: {e}")
