"""Unit tests for InMemoryCache."""
import asyncio
import pytest
from app.infrastructure.cache.in_memory_cache import InMemoryCache


@pytest.fixture
def cache():
    return InMemoryCache(default_ttl=0)  # no expiry by default


@pytest.mark.asyncio
async def test_get_miss_returns_none(cache):
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_set_and_get_roundtrip(cache):
    await cache.set("key1", {"value": 42})
    result = await cache.get("key1")
    assert result == {"value": 42}


@pytest.mark.asyncio
async def test_delete_removes_key(cache):
    await cache.set("key2", "hello")
    await cache.delete("key2")
    assert await cache.get("key2") is None


@pytest.mark.asyncio
async def test_ping_returns_true(cache):
    assert await cache.ping() is True


@pytest.mark.asyncio
async def test_ttl_expiry(cache):
    await cache.set("expiring", "val", ttl=1)
    assert await cache.get("expiring") == "val"
    await asyncio.sleep(1.1)
    assert await cache.get("expiring") is None


@pytest.mark.asyncio
async def test_clear_removes_all(cache):
    await cache.set("a", 1)
    await cache.set("b", 2)
    cache.clear()
    assert len(cache) == 0


def test_make_key_is_deterministic(cache):
    k1 = cache.make_key("query", "5")
    k2 = cache.make_key("query", "5")
    assert k1 == k2


def test_make_key_differs_for_different_inputs(cache):
    assert cache.make_key("query", "5") != cache.make_key("query", "10")
