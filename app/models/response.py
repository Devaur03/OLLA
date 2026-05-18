from pydantic import BaseModel


class SearchCandidate(BaseModel):
    """Raw result from DuckDuckGo before fetching."""
    title: str
    url: str
    snippet: str = ""


class FetchedPage(BaseModel):
    """Raw page content returned by Jina Reader."""
    title: str
    url: str
    raw_content: str


class CleanedPage(BaseModel):
    """Page content after cleaning pipeline."""
    title: str
    url: str
    content: str


class ContentChunk(BaseModel):
    """A single RAG-ready chunk of text."""
    chunk_id: int
    text: str
    char_count: int


class ProcessedResult(BaseModel):
    """Fully processed result before final ranking."""
    title: str
    url: str
    content: str
    chunks: list[ContentChunk]
    score: float = 0.0


class SearchResult(BaseModel):
    """A single ranked result in the final response."""
    rank: int
    title: str
    url: str
    content: str
    chunks: list[ContentChunk]
    score: float
    char_count: int
    chunk_count: int


class SearchResponse(BaseModel):
    """The complete structured response returned to the client."""
    query: str
    total_results: int
    processing_time_ms: int
    results: list[SearchResult]
    citations_markdown: str = ""
    citations_json: list[dict] = []


class ComponentHealth(BaseModel):
    """Health status of a single backing service."""
    status: str          # "ok" | "slow" | "error"
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Deep health check response including per-component latency."""
    status: str          # "ok" | "degraded"
    version: str
    service: str
    components: dict[str, ComponentHealth] = {}
