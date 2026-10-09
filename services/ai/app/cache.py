"""
Cache Service Module
Handles Redis caching with fallback to database.
Implements cache-first strategy for sub-10ms responses.
"""

import logging
import json
from typing import Optional, Any, Dict
import redis.asyncio as redis
from datetime import timedelta
import hashlib
from app import config

logger = logging.getLogger(__name__)

class CacheService:
    """
    Redis Cache Manager
    Provides fast in-memory caching with TTL and fallback.
    """
    
    def __init__(self, redis_url: str, default_ttl: int = 3600):
        """
        Initialize cache service.
        
        Args:
            redis_url: Redis connection URL (redis://password@host:port/db)
            default_ttl: Default time-to-live in seconds (1 hour)
        """
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.client: Optional[redis.Redis] = None
        self.stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0
        }
    
    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.client = await redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            await self.client.ping()
            logger.info("✅ Redis cache connected")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.client = None
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("✅ Redis connection closed")
    
    def _make_key(self, prefix: str, identifier: str) -> str:
        """
        Create cache key with hash for long identifiers.
        
        Args:
            prefix: Cache key prefix (e.g., 'rag:query', 'embedding')
            identifier: Unique identifier (query, embedding, etc.)
            
        Returns:
            Cache key string (max 512 chars)
        """
        if len(identifier) > 100:
            # Hash long identifiers to keep key short
            hash_val = hashlib.md5(identifier.encode()).hexdigest()[:12]
            return f"{prefix}:{hash_val}"
        return f"{prefix}:{identifier}"
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value (deserialized JSON) or None
        """
        if not self.client:
            self.stats["errors"] += 1
            return None
        
        try:
            value = await self.client.get(key)
            if value:
                self.stats["hits"] += 1
                logger.debug(f"✅ Cache HIT: {key}")
                return json.loads(value)
            
            self.stats["misses"] += 1
            logger.debug(f"❌ Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"❌ Cache read error: {e}")
            self.stats["errors"] += 1
            return None
    
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning(f"⚠️  Redis unavailable, skipping cache write: {key}")
            return False
        
        try:
            ttl = ttl or self.default_ttl
            await self.client.setex(
                key,
                ttl,
                json.dumps(value)
            )
            logger.debug(f"✅ Cached: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"❌ Cache write error: {e}")
            self.stats["errors"] += 1
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete from cache.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if deleted, False if not found or error
        """
        if not self.client:
            return False
        
        try:
            result = await self.client.delete(key)
            logger.debug(f"✅ Deleted: {key}")
            return bool(result)
        except Exception as e:
            logger.error(f"❌ Cache delete error: {e}")
            self.stats["errors"] += 1
            return False
    
    async def flush(self) -> bool:
        """Clear all cache (use with caution!)."""
        if not self.client:
            return False
        
        try:
            await self.client.flushdb()
            logger.warning("⚠️  Cache flushed!")
            return True
        except Exception as e:
            logger.error(f"❌ Cache flush error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            self.stats["hits"] / total * 100
            if total > 0 else 0
        )
        return {
            **self.stats,
            "total": total,
            "hit_rate": f"{hit_rate:.1f}%"
        }

# Global cache service instance
cache_service = CacheService(config.REDIS_URL)