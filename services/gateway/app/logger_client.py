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

async def push_log_event(action: str, user_id: str, username: str, is_admin: bool, details: dict = None):
    """
    Pushes a raw log event to Redis for the logger service to process.
    Skips logging if the user is an admin. Adds the request's IP, device and request id to the details.
    """
    from app.request_log import current, note   # where the request came from (IP, device)

    note(user_id=user_id, username=username)
    if is_admin:
        return

    details = dict(details or {})
    ctx = current.get()
    if ctx:
        details.setdefault("ip", ctx.get("ip"))
        details.setdefault("device", ctx.get("device"))
        details.setdefault("request_id", ctx.get("id"))

    try:
        r = await get_redis()
        event = {
            "action": action,
            "user_id": user_id,
            "username": username,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await r.rpush("raw_audit_logs", json.dumps(event))
    except Exception as e:
        logger.error(f"Failed to push log event to Redis: {e}")
