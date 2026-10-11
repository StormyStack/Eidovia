"""
Redis Cache Service for Gateway.
Provides hot message caching for sub-5ms chat responses using Redis.
"""

import hashlib
import json
import logging
import os
import urllib.parse
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisCache:
    """
    Manages Redis connection and hot message caching for chat queries.
    """

    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.password = os.getenv("REDIS_PASSWORD", "")
        self.db = int(os.getenv("REDIS_DB", "0"))
        # Default TTL for hot messages: 2 hours (7200 seconds)
        self.ttl = int(os.getenv("REDIS_TTL_CHAT", "7200"))
        self.client: Optional[aioredis.Redis] = None

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Lazy-connect to Redis."""
        if self.client is None:
            try:
                pwd_part = f":{urllib.parse.quote_plus(self.password)}@" if self.password else ""
                url = f"redis://{pwd_part}{self.host}:{self.port}/{self.db}"
                self.client = aioredis.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                )
                await self.client.ping()
                logger.info("Connected to Redis cache at %s:%s", self.host, self.port)
            except Exception as e:
                logger.warning("Could not connect to Redis: %s", e)
                self.client = None
        return self.client

    def _hash_key(self, question: str) -> str:
        """Create normalized Redis key for question."""
        normalized = question.strip().lower()
        md5_digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
        return f"hot_msg:{md5_digest}"

    async def get_hot_message(self, question: str) -> Optional[dict[str, Any]]:
        """
        Retrieve hot message from Redis cache.
        Returns dict with {"answer": ..., "is_on_topic": ...} or None.
        """
        client = await self.get_client()
        if not client:
            return None
        try:
            key = self._hash_key(question)
            raw = await client.get(key)
            if raw:
                logger.info("Redis cache HIT for question: %s", question[:40])
                return json.loads(raw)
        except Exception as e:
            logger.warning("Redis get_hot_message error: %s", e)
            self.client = None
        return None

    async def set_hot_message(
        self, question: str, data: dict[str, Any], ttl: Optional[int] = None
    ) -> None:
        """
        Cache hot message in Redis with TTL.
        """
        client = await self.get_client()
        if not client:
            return
        try:
            key = self._hash_key(question)
            await client.set(key, json.dumps(data), ex=ttl or self.ttl)
            logger.info("Redis cache SAVED for question: %s", question[:40])
        except Exception as e:
            logger.warning("Redis set_hot_message error: %s", e)
            self.client = None

    async def flush_hot_messages(self) -> int:
        """Clear all cached hot messages in Redis."""
        client = await self.get_client()
        if not client:
            return 0
        try:
            keys = await client.keys("hot_msg:*")
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning("Redis flush error: %s", e)
            return 0


# Global singleton
redis_cache = RedisCache()
