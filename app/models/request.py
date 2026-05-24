import re
import unicodedata
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


class SafeSearchLevel(str, Enum):
    """DuckDuckGo safe-search level. Maps directly to the ddgs `safesearch` arg."""

    STRICT = "on"  # blocks adult content entirely
    MODERATE = "moderate"  # filters explicit results (default)
    OFF = "off"  # no filtering — maximum crawl coverage


class TimeLimit(str, Enum):
    """DuckDuckGo time filter. Maps directly to the ddgs `timelimit` arg."""

    DAY = "d"
    WEEK = "w"
    MONTH = "m"
    YEAR = "y"


# Friendly region aliases → DuckDuckGo region codes.
REGION_ALIASES: dict[str, str] = {
    "wt": "wt-wt",
    "world": "wt-wt",
    "wt-wt": "wt-wt",
    "in": "in-en",
    "us": "us-en",
    "uk": "uk-en",
    "ca": "ca-en",
    "au": "au-en",
    "de": "de-de",
    "fr": "fr-fr",
}


def _sanitize_query(value: str) -> str:
    """
    Clean a raw query string:
    - Strip leading/trailing whitespace
    - Normalize Unicode to NFC (handles composed vs decomposed forms)
    - Remove ASCII control characters (0x00–0x1F, 0x7F) except normal whitespace
    - Collapse internal whitespace runs to a single space
    - Reject strings that are purely punctuation / symbols after cleaning
    """
    # Normalize unicode
    value = unicodedata.normalize("NFC", value).strip()

    # Strip control characters (keep \t \n \r as they collapse to spaces next)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

    # Collapse whitespace
    value = re.sub(r"\s+", " ", value).strip()

    # Reject if nothing meaningful remains (only punctuation/symbols)
    if value and not re.search(r"[a-zA-Z0-9À-ɏ]", value):
        raise ValueError(
            "Query must contain at least one letter or number. "
            "Queries made up entirely of punctuation or symbols are not supported."
        )

    return value


class SearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The search query string",
        examples=["how does vector search work in RAG systems"],
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of web pages to retrieve and process",
    )
    max_chars_per_page: int = Field(
        default=8000,
        ge=500,
        le=50000,
        description="Maximum characters to extract per page",
    )
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Target character length per chunk",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=200,
        description="Character overlap between consecutive chunks",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score threshold (0.0 to 1.0)",
    )
    safesearch: SafeSearchLevel = Field(
        default=SafeSearchLevel.MODERATE,
        description="Adult-content filter level: 'on', 'moderate', or 'off'",
    )
    timelimit: TimeLimit | None = Field(
        default=None,
        description="Restrict results by recency: 'd' (day), 'w', 'm', or 'y'",
    )
    region: str = Field(
        default="wt-wt",
        description="DuckDuckGo region code or alias (e.g. 'wt-wt', 'us', 'in')",
    )
    llm_model: str | None = Field(
        default=None,
        description="Override the Ollama model used for answer synthesis "
        "(defaults to the configured OLLAMA_MODEL)",
    )

    @field_validator("query", mode="before")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return _sanitize_query(v)

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, v: str) -> str:
        if not v:
            return "wt-wt"
        return REGION_ALIASES.get(str(v).strip().lower(), str(v).strip().lower())

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "how does pgvector work for semantic search",
                "max_results": 5,
                "max_chars_per_page": 8000,
                "chunk_size": 500,
                "chunk_overlap": 50,
                "min_score": 0.0,
                "safesearch": "moderate",
                "timelimit": None,
                "region": "wt-wt",
            }
        }
    }


class RetrievalMode(str, Enum):
    """
    Hybrid retrieval modes (Phase 5).

    AUTO    — let the router decide from the query classification.
    FAST    — cache + local vector memory only; never crawl the web.
    FRESH   — always crawl the web; ignore local memory.
    HYBRID  — vector memory first, web fallback when confidence is low.
    DEEP    — force a web crawl with a wider result set (deep research).
    """

    AUTO = "auto"
    FAST = "fast"
    FRESH = "fresh"
    HYBRID = "hybrid"
    DEEP = "deep"


class HybridSearchRequest(BaseModel):
    """Request for the confidence-routed hybrid retrieval endpoint."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The natural-language question to answer",
        examples=["what is a vector database"],
    )
    mode: RetrievalMode = Field(
        default=RetrievalMode.AUTO,
        description="Retrieval mode; AUTO routes from the query classification",
    )
    top_k: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Chunks to pull from local memory / results to crawl",
    )
    min_confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Memory confidence below which the router refreshes from the web",
    )
    force_refresh: bool = Field(
        default=False,
        description="Skip cache + memory and always crawl the web",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max web pages to crawl when a web fallback is triggered",
    )
    llm_model: str | None = Field(
        default=None,
        description="Override the Ollama model used for answer synthesis",
    )

    @field_validator("query", mode="before")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return _sanitize_query(v)


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Semantic search query")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of chunks to return")
    min_similarity: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum cosine similarity threshold"
    )

    @field_validator("query", mode="before")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return _sanitize_query(v)


class FeedbackLevel(str, Enum):
    """What a piece of feedback is attached to (Phase 6)."""

    ANSWER = "answer"  # the synthesized answer as a whole
    CITATION = "citation"  # one citation / source used in the answer
    CHUNK = "chunk"  # a specific retrieved text chunk
    SOURCE = "source"  # a domain / URL in general


class FeedbackType(str, Enum):
    """The signal a piece of feedback carries (Phase 6)."""

    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    INCORRECT = "incorrect"
    OUTDATED = "outdated"
    BAD_SOURCE = "bad_source"
    MISSING_CONTEXT = "missing_context"


class FeedbackRequest(BaseModel):
    """Submit feedback on an answer, citation, chunk, or source (Phase 6)."""

    level: FeedbackLevel = Field(..., description="What the feedback is attached to")
    feedback_type: FeedbackType = Field(..., description="The feedback signal")
    query_id: str | None = Field(default=None, description="Related query UUID")
    result_id: str | None = Field(default=None, description="Related result UUID")
    chunk_id: str | None = Field(default=None, description="Related chunk UUID")
    source_url: str | None = Field(default=None, description="Related source URL")
    comment: str | None = Field(
        default=None, max_length=2000, description="Optional free-text note"
    )

    @field_validator("comment", mode="before")
    @classmethod
    def _trim_comment(cls, v):
        return v.strip() if isinstance(v, str) and v.strip() else None

    @model_validator(mode="after")
    def _check_target(self):
        """Ensure the feedback identifies *something* it can act on."""
        if self.level == FeedbackLevel.CHUNK and not self.chunk_id:
            raise ValueError("chunk-level feedback requires 'chunk_id'")
        if self.level == FeedbackLevel.ANSWER and not self.query_id:
            raise ValueError("answer-level feedback requires 'query_id'")
        if self.level in (FeedbackLevel.CITATION, FeedbackLevel.SOURCE) and not (
            self.result_id or self.source_url
        ):
            raise ValueError(
                f"{self.level.value}-level feedback requires 'result_id' or 'source_url'"
            )
        return self


class GraphSearchRequest(BaseModel):
    """Multi-hop knowledge-graph retrieval request."""

    query: str = Field(..., min_length=3, max_length=500, description="Graph search query")
    hops: int = Field(default=2, ge=1, le=4, description="Number of edges to traverse")
    seed_k: int = Field(default=5, ge=1, le=20, description="Seed chunks via vector similarity")
    top_k: int = Field(default=20, ge=1, le=100, description="Max chunks to return")
    min_similarity: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum seed cosine similarity"
    )

    @field_validator("query", mode="before")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return _sanitize_query(v)
