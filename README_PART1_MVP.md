# Hybrid Search for Agents — Part 1: MVP Build Instructions
## Execution Guide for Claude (Phase 1 — Working Prototype)

---

## IMPORTANT: READ THIS FIRST

This document is a complete, self-contained execution guide. Every file, every line of code, every command is specified. Follow it top to bottom without skipping steps. Do not invent file paths, class names, or method signatures that differ from what is written here — consistency across modules is critical for the system to work.

When a code block says `# CREATE THIS FILE`, create exactly that file at exactly that path with exactly that content. When a command block says `RUN`, execute it in the terminal.

---

## What You Are Building

A FastAPI backend that:
1. Accepts a search query via HTTP POST
2. Searches DuckDuckGo for the top URLs
3. Fetches clean markdown content from those URLs using Jina Reader (Tinyfish Fetch API)
4. Cleans the text (removes markdown noise, boilerplate, extra whitespace)
5. Splits content into overlapping chunks suitable for RAG
6. Scores and ranks results by relevance to the query
7. Returns a structured JSON response with title, URL, content, chunks, and score

---

## Final Folder Structure (What You Will Create)

```
hybrid-search-agents/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       └── search.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py
│   │   └── response.py
│   └── services/
│       ├── __init__.py
│       ├── search_service.py
│       ├── fetch_service.py
│       ├── clean_service.py
│       ├── chunk_service.py
│       └── rank_service.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_clean_service.py
│   ├── test_chunk_service.py
│   ├── test_rank_service.py
│   └── test_search_endpoint.py
├── .env.example
├── .env
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## Step 1: Create Project Root & Virtual Environment

```bash
# RUN THESE COMMANDS
mkdir hybrid-search-agents
cd hybrid-search-agents
python -m venv .venv
source .venv/bin/activate          # Linux/Mac
# OR: .venv\Scripts\activate       # Windows
```

---

## Step 2: Create `pyproject.toml`

```toml
# CREATE THIS FILE AT: hybrid-search-agents/pyproject.toml

[project]
name = "hybrid-search-agents"
version = "0.1.0"
description = "Web retrieval system for AI agents and RAG applications"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "httpx>=0.27.0",
    "duckduckgo-search>=6.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.3.0",
    "httpx>=0.27.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## Step 3: Install Dependencies

```bash
# RUN THIS COMMAND
pip install fastapi "uvicorn[standard]" httpx "duckduckgo-search>=6.0.0" pydantic pydantic-settings python-dotenv

# Install dev dependencies
pip install pytest pytest-asyncio ruff
```

---

## Step 4: Create `.env.example` and `.env`

```bash
# CREATE THIS FILE AT: hybrid-search-agents/.env.example

APP_NAME="Hybrid Search for Agents"
APP_VERSION="0.1.0"
DEBUG=false

# Search settings
MAX_SEARCH_RESULTS=5
MAX_CHARS_PER_PAGE=8000
FETCH_TIMEOUT_SECONDS=15
MAX_CONCURRENT_FETCHES=5

# Chunking settings
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50

# Jina Reader base URL (Tinyfish Fetch API - no API key needed for basic use)
FETCH_BASE_URL="https://r.jina.ai"
```

```bash
# CREATE THIS FILE AT: hybrid-search-agents/.env
# (Same content as .env.example — this is the active config file)

APP_NAME="Hybrid Search for Agents"
APP_VERSION="0.1.0"
DEBUG=false
MAX_SEARCH_RESULTS=5
MAX_CHARS_PER_PAGE=8000
FETCH_TIMEOUT_SECONDS=15
MAX_CONCURRENT_FETCHES=5
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50
FETCH_BASE_URL="https://r.jina.ai"
```

---

## Step 5: Create `.gitignore`

```gitignore
# CREATE THIS FILE AT: hybrid-search-agents/.gitignore

.venv/
__pycache__/
*.pyc
*.pyo
.env
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
htmlcov/
.coverage
```

---

## Step 6: Create All `__init__.py` Files

```bash
# RUN THESE COMMANDS to create all required directories and __init__.py files

mkdir -p app/api/routes
mkdir -p app/models
mkdir -p app/services
mkdir -p tests

touch app/__init__.py
touch app/api/__init__.py
touch app/api/routes/__init__.py
touch app/models/__init__.py
touch app/services/__init__.py
touch tests/__init__.py
```

---

## Step 7: Create `app/config.py`

```python
# CREATE THIS FILE AT: app/config.py

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Hybrid Search for Agents"
    app_version: str = "0.1.0"
    debug: bool = False

    # Search
    max_search_results: int = 5
    max_chars_per_page: int = 8000
    fetch_timeout_seconds: int = 15
    max_concurrent_fetches: int = 5

    # Chunking
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50

    # Fetch API
    fetch_base_url: str = "https://r.jina.ai"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

---

## Step 8: Create Pydantic Models

### 8a. Create `app/models/request.py`

```python
# CREATE THIS FILE AT: app/models/request.py

from pydantic import BaseModel, Field


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
```

### 8b. Create `app/models/response.py`

```python
# CREATE THIS FILE AT: app/models/response.py

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


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    service: str
```

---

## Step 9: Create All Five Services

### 9a. Create `app/services/search_service.py`

```python
# CREATE THIS FILE AT: app/services/search_service.py
#
# PURPOSE: Query DuckDuckGo and return a filtered list of candidate URLs.
# Uses duckduckgo-search (DDGS) library — no API key required.
# Fetches 2x requested results to allow for filtering invalid URLs.

import logging
from duckduckgo_search import DDGS
from app.models.response import SearchCandidate

logger = logging.getLogger(__name__)

# Domains that typically don't contain useful readable text for RAG
BLOCKED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
    "reddit.com/r/",
    "pinterest.com",
    "linkedin.com/in/",
]


class SearchService:
    """
    Wraps DuckDuckGo text search and returns filtered SearchCandidate objects.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    async def search(self, query: str) -> list[SearchCandidate]:
        """
        Search DuckDuckGo for the query and return up to max_results valid candidates.

        Args:
            query: The search query string.

        Returns:
            List of SearchCandidate objects with title, url, snippet.
            Returns empty list if search fails — caller should handle this gracefully.
        """
        candidates: list[SearchCandidate] = []

        try:
            # Fetch 3x requested results so we have enough after filtering
            fetch_count = self.max_results * 3

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=fetch_count))

            for result in raw_results:
                url = result.get("href", "")
                if not self._is_valid_url(url):
                    continue

                candidates.append(
                    SearchCandidate(
                        title=result.get("title", "Untitled"),
                        url=url,
                        snippet=result.get("body", ""),
                    )
                )

                if len(candidates) >= self.max_results:
                    break

            logger.info(f"SearchService: found {len(candidates)} candidates for '{query}'")
            return candidates

        except Exception as e:
            logger.error(f"SearchService: DuckDuckGo search failed: {e}")
            return []

    def _is_valid_url(self, url: str) -> bool:
        """
        Returns True if the URL is a valid, fetchable web page.
        Rejects non-HTTP URLs and blocked domains.
        """
        if not url:
            return False
        if not url.startswith(("http://", "https://")):
            return False
        return not any(blocked in url for blocked in BLOCKED_DOMAINS)
```

---

### 9b. Create `app/services/fetch_service.py`

```python
# CREATE THIS FILE AT: app/services/fetch_service.py
#
# PURPOSE: Fetch clean markdown content from URLs using Jina Reader.
# Jina Reader (r.jina.ai) is a free service that takes any URL and returns
# clean, readable text/markdown — no scraping or HTML parsing needed.
#
# Usage: GET https://r.jina.ai/https://example.com
# Returns: clean markdown text of that page
#
# All fetches are done concurrently with asyncio + httpx.
# A semaphore limits max concurrent requests to avoid being rate-limited.

import asyncio
import logging
import httpx
from app.models.response import SearchCandidate, FetchedPage
from app.config import settings

logger = logging.getLogger(__name__)


class FetchService:
    """
    Fetches clean markdown content from a list of URLs concurrently.
    Uses Jina Reader API (r.jina.ai) as the extraction backend.
    """

    def __init__(
        self,
        timeout: int | None = None,
        max_concurrent: int | None = None,
    ):
        self.timeout = timeout or settings.fetch_timeout_seconds
        self.max_concurrent = max_concurrent or settings.max_concurrent_fetches
        self.base_url = settings.fetch_base_url  # "https://r.jina.ai"
        # Semaphore limits how many requests run at the same time
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def fetch_all(
        self,
        candidates: list[SearchCandidate],
        max_chars: int = 8000,
    ) -> list[FetchedPage]:
        """
        Fetch content from all candidate URLs concurrently.

        Args:
            candidates: List of SearchCandidate objects (title + url).
            max_chars: Truncate each page's content to this many characters.

        Returns:
            List of FetchedPage objects for successfully fetched pages.
            Failed fetches are silently dropped.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "HybridSearchAgent/1.0",
                "Accept": "text/plain, text/markdown",
                # X-Return-Format tells Jina to return markdown
                "X-Return-Format": "markdown",
            },
        ) as client:
            tasks = [
                self._fetch_one(client, candidate, max_chars)
                for candidate in candidates
            ]
            # return_exceptions=True prevents one failure from cancelling everything
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None values and exceptions
        pages = [r for r in raw_results if isinstance(r, FetchedPage)]
        logger.info(
            f"FetchService: fetched {len(pages)}/{len(candidates)} pages successfully"
        )
        return pages

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        candidate: SearchCandidate,
        max_chars: int,
    ) -> FetchedPage | None:
        """
        Fetch a single URL through Jina Reader.
        Uses semaphore to limit concurrent requests.
        Returns None on any failure.
        """
        async with self._semaphore:
            try:
                # Jina Reader format: https://r.jina.ai/{target_url}
                jina_url = f"{self.base_url}/{candidate.url}"

                response = await client.get(jina_url)
                response.raise_for_status()

                content = response.text

                # Truncate to max_chars — further processing happens downstream
                if len(content) > max_chars:
                    content = content[:max_chars]

                if not content.strip():
                    logger.debug(f"FetchService: empty content from {candidate.url}")
                    return None

                return FetchedPage(
                    title=candidate.title,
                    url=candidate.url,
                    raw_content=content,
                )

            except httpx.TimeoutException:
                logger.warning(f"FetchService: timeout fetching {candidate.url}")
                return None
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"FetchService: HTTP {e.response.status_code} for {candidate.url}"
                )
                return None
            except Exception as e:
                logger.warning(f"FetchService: failed to fetch {candidate.url}: {e}")
                return None
```

---

### 9c. Create `app/services/clean_service.py`

```python
# CREATE THIS FILE AT: app/services/clean_service.py
#
# PURPOSE: Clean raw markdown/text from Jina Reader into dense,
# coherent plain text suitable for chunking and ranking.
#
# Cleaning steps (in order):
# 1. Unicode normalization (NFKC)
# 2. Remove markdown syntax artifacts (images, headers, code blocks, etc.)
# 3. Clean up hyperlinks (keep anchor text, remove URL)
# 4. Remove boilerplate patterns (cookie notices, newsletter prompts, etc.)
# 5. Collapse excessive whitespace
# 6. Strip leading/trailing whitespace

import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

# Common boilerplate patterns found on most web pages
# These are removed because they add noise without informational value
BOILERPLATE_PATTERNS = [
    r"cookie\s+(policy|notice|consent|preferences)[\s\S]{0,200}",
    r"accept\s+all\s+cookies[\s\S]{0,100}",
    r"we\s+use\s+cookies[\s\S]{0,200}",
    r"subscribe\s+to\s+(our\s+)?newsletter[\s\S]{0,200}",
    r"sign\s+up\s+for\s+(our\s+)?newsletter[\s\S]{0,200}",
    r"all\s+rights\s+reserved[\s\S]{0,100}",
    r"©\s*\d{4}[\s\S]{0,100}",
    r"privacy\s+policy[\s\S]{0,50}",
    r"terms\s+of\s+service[\s\S]{0,50}",
    r"advertisement[\s\S]{0,50}",
    r"sponsored\s+content[\s\S]{0,50}",
    r"share\s+(this\s+)?(article|post|page)[\s\S]{0,100}",
    r"follow\s+us\s+on[\s\S]{0,100}",
    r"related\s+articles[\s\S]{0,50}",
    r"you\s+might\s+also\s+like[\s\S]{0,50}",
]


class CleanService:
    """
    Cleans raw markdown text into clean prose suitable for RAG chunking.
    All methods are pure functions — no state, safe for concurrent use.
    """

    def clean(self, raw: str) -> str:
        """
        Run the full cleaning pipeline on raw text.

        Args:
            raw: Raw text/markdown from Jina Reader.

        Returns:
            Cleaned plain text. Returns empty string if input is empty or
            becomes empty after cleaning.
        """
        if not raw or not raw.strip():
            return ""

        text = raw

        # Step 1: Normalize unicode characters
        text = self._normalize_unicode(text)

        # Step 2: Remove markdown image syntax entirely (no useful text)
        text = self._remove_images(text)

        # Step 3: Remove code blocks (inline and fenced) — usually not useful for RAG
        text = self._remove_code_blocks(text)

        # Step 4: Convert hyperlinks to just their anchor text
        text = self._clean_links(text)

        # Step 5: Remove markdown headers (keep the text, remove ## symbols)
        text = self._remove_headers(text)

        # Step 6: Remove bold/italic markers (keep the text)
        text = self._remove_emphasis(text)

        # Step 7: Remove bullet list markers
        text = self._remove_list_markers(text)

        # Step 8: Remove table formatting
        text = self._remove_tables(text)

        # Step 9: Remove boilerplate
        text = self._remove_boilerplate(text)

        # Step 10: Collapse whitespace
        text = self._collapse_whitespace(text)

        result = text.strip()
        logger.debug(f"CleanService: {len(raw)} chars → {len(result)} chars after cleaning")
        return result

    # --- Private cleaning methods ---

    def _normalize_unicode(self, text: str) -> str:
        """NFKC normalization: converts ligatures, compatibility chars, etc."""
        return unicodedata.normalize("NFKC", text)

    def _remove_images(self, text: str) -> str:
        """Remove markdown image syntax: ![alt text](url)"""
        return re.sub(r"!\[.*?\]\(.*?\)", "", text, flags=re.DOTALL)

    def _remove_code_blocks(self, text: str) -> str:
        """Remove fenced code blocks (```...```) and inline code (`...`)."""
        # Fenced blocks first
        text = re.sub(r"```[\s\S]*?```", "", text)
        # Then inline code
        text = re.sub(r"`[^`\n]+`", "", text)
        return text

    def _clean_links(self, text: str) -> str:
        """
        Convert [anchor text](url) to just 'anchor text'.
        Also handles bare URLs by removing them.
        """
        # Markdown links: keep anchor text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Bare URLs: remove entirely
        text = re.sub(r"https?://\S+", "", text)
        return text

    def _remove_headers(self, text: str) -> str:
        """Remove markdown header markers (## etc) but keep the header text."""
        return re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    def _remove_emphasis(self, text: str) -> str:
        """Remove **bold** and *italic* markers but keep text content."""
        # Bold (** or __)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"__(.+?)__", r"\1", text, flags=re.DOTALL)
        # Italic (* or _)
        text = re.sub(r"\*(.+?)\*", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"_(.+?)_", r"\1", text, flags=re.DOTALL)
        # Strikethrough
        text = re.sub(r"~~(.+?)~~", r"\1", text, flags=re.DOTALL)
        return text

    def _remove_list_markers(self, text: str) -> str:
        """Remove bullet/list markers (-, *, >) at line starts."""
        return re.sub(r"^\s*[-*>]\s+", "", text, flags=re.MULTILINE)

    def _remove_tables(self, text: str) -> str:
        """Remove markdown table formatting (pipes and dashes)."""
        # Remove table separator rows (|---|---|)
        text = re.sub(r"^\s*\|[-:\s|]+\|\s*$", "", text, flags=re.MULTILINE)
        # Remove pipe characters from table rows
        text = re.sub(r"\|", " ", text)
        return text

    def _remove_boilerplate(self, text: str) -> str:
        """Remove common web page boilerplate text."""
        for pattern in BOILERPLATE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        return text

    def _collapse_whitespace(self, text: str) -> str:
        """
        Normalize whitespace:
        - Max 2 consecutive newlines (1 blank line between paragraphs)
        - Max 1 space between words
        - Remove trailing whitespace per line
        """
        # Remove trailing spaces on each line
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
        # Collapse 3+ newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse multiple spaces to one
        text = re.sub(r" {2,}", " ", text)
        return text
```

---

### 9d. Create `app/services/chunk_service.py`

```python
# CREATE THIS FILE AT: app/services/chunk_service.py
#
# PURPOSE: Split cleaned text into overlapping chunks for RAG.
#
# Strategy: Paragraph-aware chunking with character-level fallback.
# - First tries to respect paragraph boundaries (\n\n)
# - Accumulates paragraphs into chunks up to chunk_size
# - When a paragraph would overflow the chunk, saves current chunk and starts new one
# - Carries the last `overlap` characters into the next chunk for context continuity
# - If a single paragraph is larger than chunk_size, splits it at sentence boundaries
#
# Why overlap? Without overlap, a fact that spans a chunk boundary would be split
# in half and lost. Overlap ensures each chunk has enough context around its edges.

import re
import logging
from app.models.response import ContentChunk

logger = logging.getLogger(__name__)


class ChunkService:
    """
    Splits cleaned text into overlapping ContentChunk objects.
    Paragraph-aware: respects natural paragraph boundaries where possible.
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """
        Args:
            chunk_size: Target character length for each chunk.
            overlap: Number of characters to carry from end of previous chunk
                     into the start of the next chunk.
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[ContentChunk]:
        """
        Split text into overlapping chunks.

        Args:
            text: Cleaned plain text (output of CleanService).

        Returns:
            List of ContentChunk objects. Returns empty list for empty/short text.
        """
        if not text or not text.strip():
            return []

        # If entire text fits in one chunk, return it directly
        if len(text) <= self.chunk_size:
            return [ContentChunk(chunk_id=0, text=text.strip(), char_count=len(text.strip()))]

        # Split into paragraphs (double newline = paragraph boundary)
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

        chunks: list[ContentChunk] = []
        current_text = ""
        chunk_id = 0

        for paragraph in paragraphs:
            # If adding this paragraph keeps us within chunk_size, accumulate it
            prospective = (current_text + "\n\n" + paragraph).strip() if current_text else paragraph

            if len(prospective) <= self.chunk_size:
                current_text = prospective

            else:
                # Save current chunk if it has content
                if current_text:
                    chunks.append(
                        ContentChunk(
                            chunk_id=chunk_id,
                            text=current_text,
                            char_count=len(current_text),
                        )
                    )
                    chunk_id += 1

                    # Build overlap: take last N chars of saved chunk as prefix for next
                    overlap_text = current_text[-self.overlap:] if self.overlap > 0 else ""
                    current_text = (overlap_text + " " + paragraph).strip() if overlap_text else paragraph

                else:
                    # Paragraph itself is larger than chunk_size — split it
                    sub_chunks = self._split_large_paragraph(paragraph, chunk_id)
                    chunks.extend(sub_chunks)
                    chunk_id += len(sub_chunks)

                    # Use last sub-chunk's end as overlap for next paragraph
                    if sub_chunks:
                        last = sub_chunks[-1].text
                        current_text = last[-self.overlap:] if self.overlap > 0 else ""
                    else:
                        current_text = ""

        # Don't forget the last accumulated chunk
        if current_text.strip():
            chunks.append(
                ContentChunk(
                    chunk_id=chunk_id,
                    text=current_text.strip(),
                    char_count=len(current_text.strip()),
                )
            )

        logger.debug(
            f"ChunkService: split {len(text)} chars into {len(chunks)} chunks "
            f"(size={self.chunk_size}, overlap={self.overlap})"
        )
        return chunks

    def _split_large_paragraph(self, paragraph: str, start_id: int) -> list[ContentChunk]:
        """
        Fallback: split a paragraph that is larger than chunk_size.
        Tries to split at sentence boundaries (. ! ?) first.
        Falls back to hard character split if no sentence boundaries found.
        """
        chunks: list[ContentChunk] = []
        chunk_id = start_id

        # Try sentence-level splitting
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)

        current = ""
        for sentence in sentences:
            prospective = (current + " " + sentence).strip() if current else sentence

            if len(prospective) <= self.chunk_size:
                current = prospective
            else:
                if current:
                    chunks.append(ContentChunk(
                        chunk_id=chunk_id,
                        text=current,
                        char_count=len(current),
                    ))
                    chunk_id += 1
                    overlap_text = current[-self.overlap:] if self.overlap > 0 else ""
                    current = (overlap_text + " " + sentence).strip() if overlap_text else sentence
                else:
                    # Even a single sentence exceeds chunk_size — hard split
                    for i in range(0, len(sentence), self.chunk_size - self.overlap):
                        segment = sentence[i : i + self.chunk_size]
                        if segment.strip():
                            chunks.append(ContentChunk(
                                chunk_id=chunk_id,
                                text=segment.strip(),
                                char_count=len(segment.strip()),
                            ))
                            chunk_id += 1

        if current.strip():
            chunks.append(ContentChunk(
                chunk_id=chunk_id,
                text=current.strip(),
                char_count=len(current.strip()),
            ))

        return chunks
```

---

### 9e. Create `app/services/rank_service.py`

```python
# CREATE THIS FILE AT: app/services/rank_service.py
#
# PURPOSE: Score each result by relevance to the original query and sort them.
#
# Scoring formula (MVP — keyword-based, no embeddings):
#   final_score = (tf_idf_score * 0.6) + (title_match_score * 0.3) + (density_bonus * 0.1)
#
# - tf_idf_score: How often query terms appear in content relative to total words
# - title_match_score: Fraction of query terms found in the page title
# - density_bonus: Longer content gets a small bonus (up to 0.1) — more content = richer source
#
# All scores are normalized to 0.0–1.0.
# This is intentionally simple and replaceable with embedding cosine similarity in Phase 2.

import math
import logging
from collections import Counter
from app.models.response import ProcessedResult

logger = logging.getLogger(__name__)

# Words to ignore when tokenizing (common English stop words)
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "this",
    "that", "these", "those", "it", "its", "not", "no", "nor", "so",
}


class RankService:
    """
    Scores ProcessedResult objects by relevance to a query and returns them sorted.
    """

    def rank(
        self,
        query: str,
        results: list[ProcessedResult],
    ) -> list[ProcessedResult]:
        """
        Score and sort results by relevance.

        Args:
            query: The original search query.
            results: List of ProcessedResult objects to rank.

        Returns:
            Same list, sorted descending by score (highest relevance first).
            Each result's .score field is set in place.
        """
        if not results:
            return []

        query_terms = self._tokenize(query)

        if not query_terms:
            # No meaningful terms — return as-is with score 0
            for result in results:
                result.score = 0.0
            return results

        for result in results:
            result.score = self._compute_score(query_terms, result)

        ranked = sorted(results, key=lambda r: r.score, reverse=True)

        logger.debug(
            f"RankService: ranked {len(ranked)} results for '{query}' — "
            f"top score: {ranked[0].score:.4f}"
        )
        return ranked

    def _compute_score(self, query_terms: list[str], result: ProcessedResult) -> float:
        """
        Compute a relevance score for a single result.
        Returns float in [0.0, 1.0].
        """
        content_score = self._tf_idf_score(query_terms, result.content)
        title_score = self._title_match_score(query_terms, result.title)
        density_bonus = self._density_bonus(result.content)

        final = (content_score * 0.6) + (title_score * 0.3) + (density_bonus * 0.1)
        return round(min(final, 1.0), 4)

    def _tf_idf_score(self, query_terms: list[str], content: str) -> float:
        """
        Compute a TF-IDF-inspired score for query terms in content.
        Uses a simplified IDF (no corpus — self-referential dampening).
        """
        if not content:
            return 0.0

        content_tokens = self._tokenize(content)
        if not content_tokens:
            return 0.0

        token_counts = Counter(content_tokens)
        total_tokens = len(content_tokens)

        term_scores = []
        for term in query_terms:
            count = token_counts.get(term, 0)
            # TF: frequency in this document
            tf = count / total_tokens
            # IDF proxy: rare terms score higher; log dampens very frequent terms
            idf = math.log(1 + (total_tokens / (1 + count)))
            term_scores.append(tf * idf)

        raw_score = sum(term_scores) / len(query_terms)

        # Normalize to 0–1 with a reasonable cap
        # Typical raw TF-IDF scores are in range 0.0001–0.05
        return min(raw_score * 50, 1.0)

    def _title_match_score(self, query_terms: list[str], title: str) -> float:
        """
        Score how many query terms appear in the page title.
        Title matches are strong signals — given 30% weight.
        """
        if not title or not query_terms:
            return 0.0

        title_tokens = set(self._tokenize(title))
        matches = sum(1 for term in query_terms if term in title_tokens)
        return matches / len(query_terms)

    def _density_bonus(self, content: str) -> float:
        """
        Small bonus for content-rich pages.
        Pages with 5000+ characters get full bonus (0.1).
        """
        return min(len(content) / 5000, 1.0)

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text into lowercase words, removing stop words and short tokens.
        """
        words = text.lower().split()
        return [
            w.strip(".,!?;:\"'()[]{}") 
            for w in words 
            if len(w) > 2 and w not in STOP_WORDS
        ]
```

---

## Step 10: Create API Routes

### 10a. Create `app/api/dependencies.py`

```python
# CREATE THIS FILE AT: app/api/dependencies.py

from app.config import settings


def get_settings():
    return settings
```

### 10b. Create `app/api/routes/health.py`

```python
# CREATE THIS FILE AT: app/api/routes/health.py

from fastapi import APIRouter
from app.models.response import HealthResponse
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint. Returns 200 if the service is running."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        service=settings.app_name,
    )
```

### 10c. Create `app/api/routes/search.py`

```python
# CREATE THIS FILE AT: app/api/routes/search.py

import time
import logging
from fastapi import APIRouter, HTTPException

from app.models.request import SearchRequest
from app.models.response import SearchResponse, SearchResult, ProcessedResult
from app.services.search_service import SearchService
from app.services.fetch_service import FetchService
from app.services.clean_service import CleanService
from app.services.chunk_service import ChunkService
from app.services.rank_service import RankService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Main search endpoint.

    Pipeline:
    1. DuckDuckGo search → candidate URLs
    2. Concurrent Jina Reader fetch → raw markdown
    3. Clean → remove noise
    4. Chunk → RAG-ready segments
    5. Rank → sort by relevance score
    6. Return structured JSON

    Returns 404 if no results found, 503 if pipeline fails.
    """
    start_time = time.monotonic()

    logger.info(f"Search request: '{request.query}' (max_results={request.max_results})")

    try:
        # --- STEP 1: Search ---
        search_service = SearchService(max_results=request.max_results)
        candidates = await search_service.search(request.query)

        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No results found for query: '{request.query}'"
            )

        logger.info(f"Found {len(candidates)} candidates")

        # --- STEP 2: Fetch ---
        fetch_service = FetchService()
        fetched_pages = await fetch_service.fetch_all(
            candidates=candidates,
            max_chars=request.max_chars_per_page,
        )

        if not fetched_pages:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch content from any search result URLs"
            )

        logger.info(f"Fetched {len(fetched_pages)} pages")

        # --- STEP 3: Clean + Chunk ---
        clean_service = CleanService()
        chunk_service = ChunkService(
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        processed_results: list[ProcessedResult] = []

        for page in fetched_pages:
            cleaned_content = clean_service.clean(page.raw_content)

            # Skip pages that become empty after cleaning
            if not cleaned_content:
                logger.debug(f"Skipping {page.url} — empty after cleaning")
                continue

            chunks = chunk_service.chunk(cleaned_content)

            processed_results.append(
                ProcessedResult(
                    title=page.title,
                    url=page.url,
                    content=cleaned_content,
                    chunks=chunks,
                    score=0.0,
                )
            )

        if not processed_results:
            raise HTTPException(
                status_code=503,
                detail="All fetched pages had empty content after cleaning"
            )

        # --- STEP 4: Rank ---
        rank_service = RankService()
        ranked_results = rank_service.rank(request.query, processed_results)

        # --- STEP 5: Filter and Build Response ---
        final_results: list[SearchResult] = []

        for rank_position, result in enumerate(ranked_results, start=1):
            # Apply minimum score filter
            if result.score < request.min_score:
                continue

            final_results.append(
                SearchResult(
                    rank=rank_position,
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    chunks=result.chunks,
                    score=result.score,
                    char_count=len(result.content),
                    chunk_count=len(result.chunks),
                )
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            f"Search complete: '{request.query}' → {len(final_results)} results "
            f"in {elapsed_ms}ms"
        )

        return SearchResponse(
            query=request.query,
            total_results=len(final_results),
            processing_time_ms=elapsed_ms,
            results=final_results,
        )

    except HTTPException:
        # Re-raise FastAPI HTTP exceptions as-is
        raise

    except Exception as e:
        logger.error(f"Unexpected error during search: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Search pipeline failed: {str(e)}"
        )
```

---

## Step 11: Create `app/main.py`

```python
# CREATE THIS FILE AT: app/main.py

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import health, search

# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    FastAPI application factory.
    Creates and configures the app instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Web retrieval system for AI agents and RAG applications. "
            "Searches the web, fetches clean content, chunks it for RAG, "
            "and returns structured JSON with relevance scores."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS — allow all origins in development
    # Restrict this in production to your specific frontend domain
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes with /api/v1 prefix
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")

    @app.on_event("startup")
    async def on_startup():
        logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Shutting down application")

    return app


app = create_app()
```

---

## Step 12: Create Tests

### 12a. Create `tests/conftest.py`

```python
# CREATE THIS FILE AT: tests/conftest.py

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
async def client():
    """Async test client for FastAPI app."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

### 12b. Create `tests/test_clean_service.py`

```python
# CREATE THIS FILE AT: tests/test_clean_service.py

import pytest
from app.services.clean_service import CleanService


@pytest.fixture
def svc():
    return CleanService()


def test_removes_markdown_headers(svc):
    result = svc.clean("## Hello World\nSome content here.")
    assert "##" not in result
    assert "Hello World" in result
    assert "Some content here" in result


def test_removes_images(svc):
    result = svc.clean("Text before ![alt](http://img.com/pic.jpg) text after.")
    assert "![" not in result
    assert "Text before" in result
    assert "text after" in result


def test_cleans_links(svc):
    result = svc.clean("Read [this article](https://example.com) for more info.")
    assert "](https://example.com)" not in result
    assert "this article" in result


def test_removes_code_blocks(svc):
    result = svc.clean("Intro text.\n```python\nprint('hello')\n```\nEnd text.")
    assert "```" not in result
    assert "Intro text" in result
    assert "End text" in result


def test_collapses_whitespace(svc):
    result = svc.clean("Line one\n\n\n\n\nLine two")
    assert "\n\n\n" not in result


def test_returns_empty_for_empty_input(svc):
    assert svc.clean("") == ""
    assert svc.clean("   ") == ""
    assert svc.clean("\n\n\n") == ""
```

### 12c. Create `tests/test_chunk_service.py`

```python
# CREATE THIS FILE AT: tests/test_chunk_service.py

import pytest
from app.services.chunk_service import ChunkService


@pytest.fixture
def svc():
    return ChunkService(chunk_size=100, overlap=10)


def test_single_chunk_for_short_text(svc):
    text = "Short text."
    chunks = svc.chunk(text)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == 0
    assert chunks[0].text == "Short text."


def test_multiple_chunks_for_long_text(svc):
    # Create text longer than chunk_size
    text = "This is a sentence. " * 20  # 400 chars
    chunks = svc.chunk(text)
    assert len(chunks) > 1


def test_chunk_ids_are_sequential(svc):
    text = "\n\n".join(["Paragraph number " + str(i) + ". " * 10 for i in range(10)])
    chunks = svc.chunk(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id == i


def test_char_count_matches_text_length(svc):
    text = "\n\n".join(["Word " * 30 for _ in range(5)])
    chunks = svc.chunk(text)
    for chunk in chunks:
        assert chunk.char_count == len(chunk.text)


def test_empty_input_returns_empty_list(svc):
    assert svc.chunk("") == []
    assert svc.chunk("   ") == []
```

### 12d. Create `tests/test_rank_service.py`

```python
# CREATE THIS FILE AT: tests/test_rank_service.py

import pytest
from app.services.rank_service import RankService
from app.models.response import ProcessedResult, ContentChunk


def make_result(title: str, content: str) -> ProcessedResult:
    return ProcessedResult(
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}",
        content=content,
        chunks=[ContentChunk(chunk_id=0, text=content[:100], char_count=100)],
        score=0.0,
    )


@pytest.fixture
def svc():
    return RankService()


def test_scores_are_between_0_and_1(svc):
    results = [
        make_result("Python Async", "Python supports async and await for concurrency."),
        make_result("Java Spring", "Java Spring Boot is a framework for building APIs."),
    ]
    ranked = svc.rank("python async programming", results)
    for r in ranked:
        assert 0.0 <= r.score <= 1.0


def test_relevant_result_scores_higher(svc):
    relevant = make_result(
        "Vector Search RAG",
        "Vector search is used in RAG systems to find semantically similar chunks.",
    )
    irrelevant = make_result(
        "Cooking Recipes",
        "This article covers recipes for pasta, pizza, and other Italian food.",
    )
    ranked = svc.rank("vector search RAG", [irrelevant, relevant])
    assert ranked[0].title == "Vector Search RAG"


def test_empty_results_returns_empty(svc):
    assert svc.rank("test query", []) == []


def test_results_are_sorted_descending(svc):
    results = [
        make_result(f"Result {i}", f"Content about topic number {i} " * 10)
        for i in range(5)
    ]
    ranked = svc.rank("topic content", results)
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
```

### 12e. Create `tests/test_search_endpoint.py`

```python
# CREATE THIS FILE AT: tests/test_search_endpoint.py
# NOTE: These are integration tests that make real network calls.
# Run with: pytest tests/test_search_endpoint.py -v
# Requires internet connection.

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_search_request_validation_too_short():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "hi"},  # too short (min 3 chars)
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_request_validation_max_results():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "test query", "max_results": 99},  # exceeds max of 10
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_valid_structure():
    """Integration test — makes real search. Requires internet."""
    async with AsyncClient(app=app, base_url="http://test", timeout=60.0) as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "Python FastAPI tutorial", "max_results": 2},
        )
    # Accept 200 or 404 (if DuckDuckGo returns nothing, which is rare)
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert "total_results" in data
        assert "processing_time_ms" in data
        assert isinstance(data["results"], list)

        if data["results"]:
            result = data["results"][0]
            assert "rank" in result
            assert "title" in result
            assert "url" in result
            assert "content" in result
            assert "chunks" in result
            assert "score" in result
            assert result["rank"] == 1
            assert 0.0 <= result["score"] <= 1.0
```

---

## Step 13: Run the Application

### Start the server

```bash
# RUN THIS COMMAND from the project root
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Starting Hybrid Search for Agents v0.1.0
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Test the health endpoint

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{"status": "ok", "version": "0.1.0", "service": "Hybrid Search for Agents"}
```

### Run a search

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how does pgvector work for semantic search",
    "max_results": 3,
    "chunk_size": 400,
    "chunk_overlap": 40
  }'
```

### View auto-generated API docs

Open in browser: `http://localhost:8000/docs`

---

## Step 14: Run Tests

```bash
# Run all unit tests (no network required)
pytest tests/test_clean_service.py tests/test_chunk_service.py tests/test_rank_service.py -v

# Run with coverage
pytest tests/test_clean_service.py tests/test_chunk_service.py tests/test_rank_service.py \
  --cov=app/services --cov-report=term-missing -v

# Run integration tests (requires internet)
pytest tests/test_search_endpoint.py -v -s
```

---

## Verification Checklist

Before considering Part 1 complete, verify each item:

- [ ] `GET /api/v1/health` returns `{"status": "ok"}`
- [ ] `POST /api/v1/search` with a valid query returns a JSON response
- [ ] Response contains `query`, `total_results`, `processing_time_ms`, `results`
- [ ] Each result contains `rank`, `title`, `url`, `content`, `chunks`, `score`
- [ ] Each chunk contains `chunk_id`, `text`, `char_count`
- [ ] Results are sorted by score descending (first result has highest score)
- [ ] Invalid queries (too short) return 422
- [ ] Unit tests pass for CleanService, ChunkService, RankService
- [ ] API docs render at `http://localhost:8000/docs`
- [ ] `processing_time_ms` is under 5000 for a 3-result query

---

## Common Errors & Fixes

**`ModuleNotFoundError: No module named 'duckduckgo_search'`**
```bash
pip install "duckduckgo-search>=6.0.0"
```

**`RateLimitError` or `DuckDuckGoSearchException`**
DuckDuckGo throttles aggressive requests. Add a small delay:
```python
import asyncio
await asyncio.sleep(0.5)  # Add to SearchService.search() before DDGS call
```

**`httpx.ConnectError` on Jina fetch**
Check your internet connection. Jina Reader (r.jina.ai) must be reachable.

**`422 Unprocessable Entity` on POST /search**
The request body doesn't match the schema. Ensure `query` is at least 3 characters.

**`ImportError: cannot import name 'ProcessedResult'`**
Ensure `app/models/response.py` contains the `ProcessedResult` class from Step 8b.

---

## What's Next: Part 2

Part 2 (README_PART2_SCALE.md) covers:
- PostgreSQL + SQLAlchemy for persisting queries and results
- Redis caching (repeat queries return in <50ms)
- Vector embeddings with OpenAI or local BGE model
- pgvector semantic search endpoint
- MCP server for Claude/agent tool integration
- API key authentication and rate limiting
- Docker Compose setup for the full stack
- Source credibility scoring
- Citation generation

Do not start Part 2 until all items in the Verification Checklist above are confirmed.
```

---

*End of Part 1 — MVP Build Instructions*
