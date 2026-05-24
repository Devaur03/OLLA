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
    # RAG-synthesized natural-language answer with inline [n] citations.
    answer: str = ""
    # Which local LLM produced the answer (empty if synthesis was skipped/failed).
    answer_model: str = ""
    # UUID of the stored query record — required to attach answer-level feedback.
    query_id: str | None = None


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


class FeedbackResponse(BaseModel):
    """Acknowledgement returned after recording a feedback event (Phase 6)."""
    feedback_id: str
    level: str
    feedback_type: str
    recorded: bool = True
    effects: list[str] = []   # what ranking signals this feedback updated


class FeedbackStats(BaseModel):
    """Aggregate feedback analytics (Phase 6/7 dashboard)."""
    total: int
    by_type: dict = {}
    by_level: dict = {}
    satisfaction_rate: float = 0.0   # positive / total, in [0,1]
    best_sources: list[dict] = []
    worst_sources: list[dict] = []
    most_flagged_chunks: list[dict] = []
    sources_needing_refresh: list[dict] = []


class RetrievedSource(BaseModel):
    """One source backing a hybrid answer, with its routing signals."""
    title: str
    url: str
    trust: float = 0.5
    freshness: float = 0.5
    similarity: float | None = None       # set on the memory path
    from_memory: bool = False


class HybridSearchResponse(BaseModel):
    """
    Response from the confidence-routed hybrid retrieval endpoint (Phase 5).

    `retrieval_mode` is the mode actually used after routing; `from_memory`
    tells the caller whether the answer came from local semantic memory or a
    fresh web crawl. `routing_trace` records every decision the router made.
    """
    query: str
    retrieval_mode: str               # fast | fresh | hybrid | deep
    query_class: str                  # news | recent | technical | ...
    web_required: bool
    from_memory: bool                 # answered from memory vs. fresh crawl
    confidence: float                 # memory confidence the router computed
    processing_time_ms: int
    answer: str = ""
    answer_model: str = ""
    citations_markdown: str = ""
    citations_json: list[dict] = []
    results: list[SearchResult] = []
    sources: list[RetrievedSource] = []
    routing_trace: list[str] = []     # human-readable routing decisions
    # Phase 10 citation verification: share of [n] markers backed by an
    # on-topic source, and the markers that failed the check.
    citation_support: float = 0.0
    unsupported_citations: list[int] = []
    cache_hit: bool = False
    degraded: bool = False
