"""Circuit breaker pattern — prevents cascading failures in external calls.

States:
  closed    Normal operation. Failures are counted.
  open      Too many failures. Calls rejected immediately without hitting the provider.
  half_open Recovery window. One probe call is allowed through.

Usage:
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    result = await breaker.call(my_async_func, arg1, arg2)
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Any

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when a call is blocked because the circuit is open."""


class CircuitBreaker:
    """Simple async circuit breaker.

    Args:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout:  Seconds to wait before trying a probe call.
        expected_exception: Exception type that counts as a failure.
        name: Human-readable name for log messages.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
        name: str = "unnamed",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name
        self._failures = 0
        self._last_failure: datetime | None = None
        self._state = "closed"  # closed | open | half_open

    @property
    def state(self) -> str:
        return self._state

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute func(*args, **kwargs) subject to circuit breaker logic."""
        if self._state == "open":
            if (datetime.utcnow() - self._last_failure) > timedelta(seconds=self.recovery_timeout):
                self._state = "half_open"
                logger.info("CircuitBreaker[%s]: entering half-open state", self.name)
            else:
                raise CircuitBreakerOpen(
                    f"Circuit '{self.name}' is OPEN — call blocked to protect downstream."
                )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as exc:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state != "closed":
            logger.info("CircuitBreaker[%s]: closed after successful probe", self.name)
        self._failures = 0
        self._state = "closed"

    def _on_failure(self) -> None:
        self._failures += 1
        self._last_failure = datetime.utcnow()
        if self._failures >= self.failure_threshold:
            if self._state != "open":
                logger.warning(
                    "CircuitBreaker[%s]: OPEN after %d failures",
                    self.name, self._failures,
                )
            self._state = "open"
