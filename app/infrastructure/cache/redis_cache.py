"""
Redis implementation of the Cache interface.

Key design choices:
- Keys are namespaced: {prefix}:{sha256(raw_key)}
- TTL defaults to 3600s (1 hour)
- Serialises values as JSON so any JSON-able type round-trips correctly
- aioredis (redis-py >= 4.2) is used for async I/O
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.domain.interfaces.cache import Cache
from app.core.errors.exceptions import CacheError

logger = logging.getLogger(__name__)


class RedisCache(Cache):
    """
    Redis-backed Cache implementation.

    Args:
        url: Redis connection URL (e.g. redis://localhost:6379/0).
        default_ttl: Default time-to-live in seconds.
        key_prefix: Namespace prefix applied to every key.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        default_ttl: int = 3600,
        key_prefix: str = "hs",
    ) -> None:
        self._url = url
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix
        self._client: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Cache interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        client = await self._get_client()
        try:
            raw = await client.get(self._ns(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("RedisCache.get failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        client = await self._get_client()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        try:
            serialised = json.dumps(value)
            await client.setex(self._ns(key), effective_ttl, serialised)
        except Exception as exc:
            raise CacheError("RedisCache.set failed: " + str(exc)) from exc

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        try:
            await client.delete(self._ns(key))
        except Exception as exc:
            raise CacheError("RedisCache.delete failed: " + str(exc)) from exc

    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            return await client.ping()
        except Exception:
            return False

    def make_key(self, *parts: str) -> str:
        raw = ":".join(parts)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return digest

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ns(self, key: str) -> str:
        return "{}:{}".format(self._key_prefix, key)

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
