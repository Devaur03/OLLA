"""Exponential backoff retry decorator for async functions."""
import asyncio
import logging
from typing import Callable, Type
from functools import wraps

logger = logging.getLogger(__name__)


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator: retry an async function with exponential backoff.

    Args:
        max_attempts: Total number of attempts (including first).
        base_delay:   Initial wait in seconds (doubles each retry).
        max_delay:    Cap on wait time.
        exceptions:   Only retry these exception types.

    Usage:
        @async_retry(max_attempts=3, exceptions=(httpx.TimeoutException,))
        async def fetch(url: str) -> str:
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        logger.error(
                            "retry[%s]: all %d attempts failed. Last error: %s",
                            func.__name__, max_attempts, exc,
                        )
                        raise
                    wait = min(delay, max_delay)
                    logger.warning(
                        "retry[%s]: attempt %d/%d failed (%s). Retrying in %.1fs...",
                        func.__name__, attempt, max_attempts, exc, wait,
                    )
                    await asyncio.sleep(wait)
                    delay *= 2
        return wrapper
    return decorator
