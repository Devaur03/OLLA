"""Custom exception hierarchy for Hybrid Search.

Using typed exceptions instead of bare Exception makes error handling explicit
and lets FastAPI handlers return consistent JSON error bodies.
"""


class HybridSearchError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class SearchProviderError(HybridSearchError):
    """Search provider (DDG, Brave) failed after all retries."""


class RateLimitError(SearchProviderError):
    """Provider returned a rate limit response."""
    def __init__(self, provider: str, retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__(
            f"{provider} rate limit hit."
            + (f" Retry after {retry_after}s." if retry_after else "")
        )


class ContentFetchError(HybridSearchError):
    """Content fetcher (Jina, Playwright) failed to retrieve a URL."""
    def __init__(self, url: str, reason: str):
        super().__init__(f"Failed to fetch {url}: {reason}", {"url": url})


class EmbeddingError(HybridSearchError):
    """Embedding model failed to produce a vector."""


class CacheError(HybridSearchError):
    """Cache backend encountered an error (non-fatal — caller should proceed without cache)."""


class PersistenceError(HybridSearchError):
    """Database persistence failed (non-fatal — search result is still returned)."""


class ValidationError(HybridSearchError):
    """Input validation failed."""
    def __init__(self, field: str, reason: str):
        super().__init__(f"Invalid value for '{field}': {reason}", {"field": field})


class ConfigurationError(HybridSearchError):
    """Required configuration is missing or invalid at startup."""
