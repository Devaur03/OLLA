from dataclasses import dataclass, field


@dataclass
class SearchQuery:
    text: str
    max_results: int = 5
    max_chars_per_page: int = 8000
    chunk_size: int = 500
    chunk_overlap: int = 50
    min_score: float = 0.0

    def as_cache_params(self) -> dict:
        return {
            "max_results": self.max_results,
            "max_chars_per_page": self.max_chars_per_page,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }


@dataclass
class Chunk:
    chunk_id: int
    text: str
    char_count: int
    embedding: list = field(default_factory=list)


@dataclass
class RankedResult:
    rank: int
    title: str
    url: str
    content: str
    chunks: list
    score: float
    char_count: int
    chunk_count: int
