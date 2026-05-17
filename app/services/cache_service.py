import json
import hashlib
import logging
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Redis-backed cache for SearchResponse objects."""

    def __init__(self):
        self.client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        self.ttl = settings.cache_ttl_seconds

    def make_key(self, query: str, params: dict) -> str:
        """
        Generate a unique cache key for a query + params combination.
        Keys are SHA-256 hashes to keep them fixed-length and collision-resistant.
        """
        raw = f"{query.lower().strip()}:{json.dumps(params, sort_keys=True)}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"search:{digest}"

    async def get(self, key: str) -> dict | None:
        """
        Retrieve a cached response.

        Returns:
            Parsed dict if cache hit, None if cache miss or Redis error.
        """
        try:
            data = await self.client.get(key)
            if data:
                logger.debug(f"CacheService: HIT for key {key[:16]}...")
                return json.loads(data)
            logger.debug(f"CacheService: MISS for key {key[:16]}...")
            return None
        except Exception as e:
            logger.warning(f"CacheService: get failed: {e}")
            return None  # Cache failure should never break the search

    async def set(self, key: str, value: dict) -> bool:
        """
        Store a response in Redis with TTL.

        Returns:
            True on success, False on failure.
        """
        try:
            await self.client.setex(key, self.ttl, json.dumps(value))
            logger.debug(f"CacheService: SET key {key[:16]}... (TTL={self.ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"CacheService: set failed: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a specific cache key."""
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"CacheService: delete failed: {e}")
            return False

    async def flush_all(self) -> bool:
        """
        Flush all search cache keys.
        Uses SCAN to safely iterate — never calls FLUSHALL on the whole database.
        """
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self.client.scan(cursor, match="search:*", count=100)
                if keys:
                    await self.client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            logger.info(f"CacheService: flushed {deleted} keys")
            return True
        except Exception as e:
            logger.error(f"CacheService: flush_all failed: {e}")
            return False

    async def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
