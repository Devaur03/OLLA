import re
import unicodedata
from pydantic import BaseModel, Field, field_validator


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

    @field_validator("query", mode="before")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        return _sanitize_query(v)

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "how does pgvector work for semantic search",
                "max_results": 5,
                "max_chars_per_page": 8000,
                "chunk_size": 500,
                "chunk_overlap": 50,
                "min_score": 0.0,
            }
        }
    }


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
