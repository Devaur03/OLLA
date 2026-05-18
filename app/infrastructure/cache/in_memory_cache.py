"""
In-memory Cache implementation for use in unit tests and local dev.

Stores values in a plain dict with optional TTL (expiry tracked via time.monotonic).
Thread-safe enough for asyncio single-threaded use; not safe for multi-process use.
"""
from __future__ import annotations

import time
from typing import Any, Optional
import hashlib

from app.domain.interfaces.cache import Cache


class InMemoryCache(Cache):
    """
    Dict-based cache with TTL support.  No external dependencies.

    Expired entries are lazily evicted on read rather than via a background task,
    which keeps this implementation simple and test-friendly.

    Args:
        default_ttl: Default time-to-live in seconds (0 = never expires).
    """

    def __init__(self, default_ttl: int = 0) -> None:
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[Any, Optional[float]]] = {}
        # (value, expires_at_monotonic_or_None)

    # ------------------------------------------------------------------
    # Cache interface
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = (time.monotonic() + effective_ttl) if effective_ttl > 0 else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ping(self) -> bool:
        return True

    def make_key(self, *parts: str) -> str:
        raw = ":".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all entries.  Useful in test teardown."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
