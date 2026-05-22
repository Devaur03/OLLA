"""Abstract interface for persistence of search results."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class StoredSearchResult:
    """Represents a search result ready to be persisted."""
    query: str
    params: dict
    results: list
    processing_ms: int


class SearchRepository(ABC):
    """Contract every search repository must satisfy.

    Implementations: PostgresSearchRepository.
    """

    @abstractmethod
    async def save(self, payload: StoredSearchResult) -> str:
        """Persist a search result set.

        Returns:
            The UUID of the saved query record.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the repository is reachable."""
