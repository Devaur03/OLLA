"""Abstract interface for caching."""
from abc import ABC, abstractmethod
from typing import Any


class Cache(ABC):
    """Contract every cache backend must satisfy.

    Implementations: RedisCache, InMemoryCache (for tests/dev).
    """

    @abstractmethod
    async def get(self, key: str) -> dict | None:
        """Return cached value or None on miss/error."""

    @abstractmethod
    async def set(self, key: str, value: dict, ttl: int | None = None) -> bool:
        """Store a value. Returns True on success."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Remove a key. Returns True on success."""

    @abstractmethod
    async def ping(self) -> bool:
        """Verify the cache backend is reachable."""

    def make_key(self, *parts: str) -> str:
        """Build a namespaced cache key from parts."""
        import hashlib, json
        raw = ":".join(str(p) for p in parts)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"search:{digest}"
