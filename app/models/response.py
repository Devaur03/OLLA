from pydantic import BaseModel


class SearchCandidate(BaseModel):
    """Raw result from DuckDuckGo before fetching."""
    title: str
    url: str
    snippet: str = ""


class FetchedPage(BaseModel):
    """Raw page content returned by the fetch waterfall."""
    title: str
    url: str
    raw_content: str
    # Which method produced the content: 'jina' | 'direct' | 'snippet'.
    fetch_method: str = "jina"


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
    # Named entities extracted from the chunk (optional — empty if spaCy absent).
    entities: list[dict] = []


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


class StageTrace(BaseModel):
    """Observability record for one pipeline stage."""
    stage: str
    status: str           # 'success' | 'failed' | 'fallback' | 'skipped'
    duration_ms: int
    detail: str = ""


class SearchResponse(BaseModel):
    """The complete structured response returned to the client."""
    query: str
    total_results: int
    processing_time_ms: int
    results: list[SearchResult]
    citations_markdown: str = ""
    citations_json: list[dict] = []
    cache_hit: bool = False
    # True when one or more non-fatal stages failed but the search still returned.
    degraded: bool = False
    # Per-stage timing/status for dashboard + debugging.
    trace: list[StageTrace] = []


class ComponentHealth(BaseModel):
    """Health status of a single backing service."""
    status: str
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Deep health check response including per-component latency."""
    status: str
    version: str
    service: str
    components: dict
