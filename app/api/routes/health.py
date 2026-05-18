import time
import logging
from fastapi import APIRouter
from sqlalchemy import text
import redis.asyncio as aioredis

from app.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_redis() -> dict:
    """Ping Redis and measure round-trip latency."""
    client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        t0 = time.monotonic()
        await client.ping()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        status = "ok"
        if latency_ms > 500:
            status = "slow"
            logger.warning(
                "Redis is responding slowly (%sms). "
                "Expected <50ms. Check Redis load or network path.",
                latency_ms,
            )
        return {"status": status, "latency_ms": latency_ms}
    except Exception as e:
        logger.error(
            "Redis health check failed: %s. "
            "Is Redis running? Try: docker compose -f docker/docker-compose.yml up -d cache",
            e,
        )
        return {"status": "error", "error": str(e)}
    finally:
        await client.aclose()


async def _check_db() -> dict:
    """Run a trivial query and measure round-trip latency."""
    try:
        async with engine.connect() as conn:
            t0 = time.monotonic()
            await conn.execute(text("SELECT 1"))
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
        status = "ok"
        if latency_ms > 500:
            status = "slow"
            logger.warning(
                "PostgreSQL is responding slowly (%sms). "
                "Expected <100ms. Check DB load or connection pool saturation.",
                latency_ms,
            )
        return {"status": status, "latency_ms": latency_ms}
    except Exception as e:
        logger.error(
            "PostgreSQL health check failed: %s. "
            "Is PostgreSQL running? Try: docker compose -f docker/docker-compose.yml up -d db",
            e,
        )
        return {"status": "error", "error": str(e)}


@router.get("/health")
async def health_check():
    """
    Deep health check - probes Redis and PostgreSQL and reports latency.

    Status values per component:
      ok    - reachable and responding within normal range
      slow  - reachable but responding slowly (>500ms)
      error - unreachable or threw an exception

    Overall status:
      ok       - all components healthy
      degraded - at least one component is slow or erroring
    """
    redis_info = await _check_redis()
    db_info = await _check_db()

    all_ok = redis_info["status"] == "ok" and db_info["status"] == "ok"

    return {
        "status": "ok" if all_ok else "degraded",
        "version": settings.app_version,
        "service": settings.app_name,
        "components": {
            "redis": redis_info,
            "database": db_info,
        },
    }
