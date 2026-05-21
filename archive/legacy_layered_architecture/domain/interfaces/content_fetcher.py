"""Abstract interface for fetching clean content from URLs."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FetchedPage:
    """Clean text content retrieved from a URL."""
    url: str
    content: str           # cleaned text body
    success: bool = True
    title: str = ""
    error: str = ""


class ContentFetcher(ABC):
    """Contract every content fetcher must satisfy.

    Implementations: JinaReaderFetcher.
    Swap by injecting a different implementation — no route changes needed.
    """

    @abstractmethod
    async def fetch_all(self, urls: list[str]) -> list[FetchedPage]:
        """Fetch content from a list of URLs concurrently.

        Args:
            urls: List of URLs to fetch.

        Returns:
            One FetchedPage per URL; failed fetches have success=False and content="".
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the fetcher is reachable. Returns True if healthy."""
