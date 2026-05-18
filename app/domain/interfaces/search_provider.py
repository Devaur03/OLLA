"""Abstract interface for web search providers (DDG, Brave, Tavily, etc.)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchCandidate:
    """A raw URL candidate returned by a search provider."""
    title: str
    url: str
    snippet: str = ""


class SearchProvider(ABC):
    """Contract every search provider must satisfy.

    Implementations: DuckDuckGoSearch, BraveSearch.
    Swap providers by injecting a different implementation — no route changes needed.
    """

    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchCandidate]:
        """Execute a search and return candidate URLs.

        Args:
            query: The search query string.
            max_results: Maximum number of candidates to return.

        Returns:
            List of SearchCandidate objects, possibly empty on failure.

        Raises:
            SearchProviderError: If the provider fails after all retries.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the provider is reachable. Returns True if healthy."""
