# Hybrid Search for Agents
## Complete Project Blueprint — Architecture, Phases, Tech Stack & Implementation Guide

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [System Architecture](#3-system-architecture)
4. [Tech Stack](#4-tech-stack)
5. [Folder Structure](#5-folder-structure)
6. [API Design](#6-api-design)
7. [Core Module Design](#7-core-module-design)
8. [Data Flow & Pipeline](#8-data-flow--pipeline)
9. [Phase 1 — MVP (Working Prototype)](#9-phase-1--mvp-working-prototype)
10. [Phase 2 — Storage & Caching Layer](#10-phase-2--storage--caching-layer)
11. [Phase 3 — Semantic Search & Embeddings](#11-phase-3--semantic-search--embeddings)
12. [Phase 4 — Agent & MCP Integration](#12-phase-4--agent--mcp-integration)
13. [Phase 5 — Production Hardening](#13-phase-5--production-hardening)
14. [Phase 6 — Frontend Dashboard](#14-phase-6--frontend-dashboard)
15. [Deployment Strategy](#15-deployment-strategy)
16. [Security Considerations](#16-security-considerations)
17. [Testing Strategy](#17-testing-strategy)
18. [Performance & Scaling](#18-performance--scaling)
19. [Roadmap Summary](#19-roadmap-summary)

---

## 1. Project Overview

**Hybrid Search for Agents** is a modular, scalable web retrieval backend designed specifically for AI agents and RAG (Retrieval-Augmented Generation) pipelines. It bridges the gap between raw web search and structured, clean, agent-ready knowledge.

The system takes a natural language query, searches the web via DuckDuckGo, fetches and extracts clean content from the top results using the Tinyfish Fetch API, processes that content through a cleaning → chunking → ranking pipeline, and returns structured JSON that AI agents can directly consume — no HTML noise, no boilerplate, just relevant grounded knowledge.

### Why this matters

- LLMs hallucinate on topics beyond their training data
- Agent tools need clean, structured, reliable context — not raw HTML
- Existing solutions are either too heavy (entire RAG frameworks) or too thin (simple search wrappers)
- This project targets the sweet spot: a self-hosted, lightweight, production-capable retrieval microservice

---

## 2. Goals & Non-Goals

### MVP Goals
- Accept a user query via REST API
- Search DuckDuckGo for top URLs
- Fetch and extract clean markdown from those pages
- Clean, chunk, and rank the content
- Return structured JSON with title, URL, content, chunks, and relevance score

### Future Goals
- Persistent storage with PostgreSQL
- Redis-based caching for repeat queries
- Vector embeddings with pgvector for semantic search
- Source credibility scoring
- Citation generation
- MCP server support for AI agent tool integration
- Frontend dashboard for monitoring and manual search

### Non-Goals (for now)
- Real-time streaming responses (can be added in Phase 5)
- Support for paywalled or login-protected pages
- Browser automation (JavaScript-rendered pages)
- Multi-language support (English only in MVP)

---

## 3. System Architecture

### MVP Architecture (Phase 1)

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT / AGENT                       │
│              (curl, Python script, AI agent tool)           │
└─────────────────────────────┬───────────────────────────────┘
                              │ POST /search
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        FASTAPI APP                          │
│                    (api/routes/search.py)                   │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Search  │  │  Fetch   │  │  Clean   │  │   Rank    │  │
│  │ Service  │→ │ Service  │→ │ Service  │→ │  Service  │  │
│  │(DuckDDGo)│  │(Tinyfish)│  │(cleaner) │  │ (scorer)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│                                    │                        │
│                              ┌──────────┐                   │
│                              │  Chunk   │                   │
│                              │ Service  │                   │
│                              └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Structured JSON Response
```

### Target Architecture (Phase 3+)

```
┌───────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                              │
│   AI Agents  │  MCP Clients  │  Frontend Dashboard  │  curl/SDK  │
└───────────────────────────┬───────────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────────┐
│                      API GATEWAY (FastAPI)                        │
│            Auth Middleware │ Rate Limiting │ Request Logging       │
└──────┬──────────────┬──────────────┬───────────────┬─────────────┘
       │              │              │               │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
│   Search    │ │   Fetch    │ │   RAG    │ │    MCP      │
│   Router    │ │   Router   │ │  Router  │ │   Router    │
└──────┬──────┘ └─────┬──────┘ └────┬─────┘ └──────┬──────┘
       │              │              │               │
┌──────▼──────────────▼──────────────▼───────────────▼──────┐
│                    SERVICE LAYER                           │
│  SearchSvc │ FetchSvc │ CleanSvc │ ChunkSvc │ RankSvc     │
│  EmbedSvc  │ CiteSvc  │ CredSvc  │ CacheSvc │ StoreSvc    │
└──────┬──────────────────────────────────────┬─────────────┘
       │                                      │
┌──────▼──────────┐                  ┌────────▼────────────┐
│  External APIs  │                  │   Storage Layer     │
│  DuckDuckGo     │                  │  PostgreSQL+pgvector │
│  Tinyfish Fetch │                  │  Redis Cache        │
│  Embed APIs     │                  │  S3 (optional)      │
└─────────────────┘                  └─────────────────────┘
```

---

## 4. Tech Stack

### Core (MVP)

| Layer | Technology | Reason |
|---|---|---|
| API Framework | FastAPI | Async-native, auto OpenAPI docs, Pydantic validation |
| Runtime | Python 3.11+ | Mature async support, rich AI/NLP ecosystem |
| HTTP Client | httpx | Async HTTP with connection pooling |
| Web Search | duckduckgo-search (DDGS) | Free, no API key needed for basic use |
| Content Extraction | Tinyfish Fetch API | Returns clean markdown from any URL |
| Data Validation | Pydantic v2 | Type-safe models, fast serialization |
| Config Management | python-dotenv | Simple .env-based config |
| Text Processing | Standard Python (re, unicodedata) | Lightweight, no heavy deps in MVP |

### Phase 2 — Storage & Caching

| Layer | Technology | Reason |
|---|---|---|
| Database | PostgreSQL 15+ | Robust, supports pgvector extension |
| ORM | SQLAlchemy 2.0 (async) | Async-native, well-maintained |
| Migrations | Alembic | Standard migration tool for SQLAlchemy |
| Cache | Redis 7+ | Fast in-memory cache, TTL support |
| Cache Client | redis-py (async) | Async Redis client |

### Phase 3 — Semantic Search

| Layer | Technology | Reason |
|---|---|---|
| Embeddings | OpenAI text-embedding-3-small or BGE-small (local) | Fast, high-quality embeddings |
| Vector Store | pgvector (PostgreSQL extension) | No separate vector DB needed |
| Similarity | cosine similarity via pgvector | Native SQL vector search |

### Phase 4 — Agent & MCP

| Layer | Technology | Reason |
|---|---|---|
| MCP Server | FastMCP or custom JSON-RPC | Model Context Protocol compliance |
| Agent SDK | Anthropic Claude Tool Use / OpenAI Function Calling | Both supported via abstraction |

### Phase 6 — Frontend

| Layer | Technology | Reason |
|---|---|---|
| Frontend | Next.js 14 + TypeScript | Modern, fast, SSR-capable |
| Styling | Tailwind CSS | Rapid UI development |
| State | Zustand | Lightweight state management |
| Charts | Recharts | Score/relevance visualization |

### DevOps & Tooling

| Tool | Purpose |
|---|---|
| Docker + Docker Compose | Local development environment |
| uv or pip-tools | Dependency management |
| Pytest + pytest-asyncio | Testing |
| Ruff | Linting and formatting |
| Pre-commit | Code quality hooks |
| GitHub Actions | CI/CD |

---

## 5. Folder Structure

### Phase 1 (MVP)

```
hybrid-search-agents/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory
│   ├── config.py                  # Settings via pydantic-settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py        # Shared FastAPI dependencies
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── search.py          # POST /search endpoint
│   │       └── health.py          # GET /health endpoint
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py             # SearchRequest Pydantic model
│   │   └── response.py            # SearchResult, SearchResponse models
│   │
│   └── services/
│       ├── __init__.py
│       ├── search_service.py      # DuckDuckGo DDGS integration
│       ├── fetch_service.py       # Tinyfish Fetch API + httpx
│       ├── clean_service.py       # Text cleaning and normalization
│       ├── chunk_service.py       # Content chunking for RAG
│       └── rank_service.py        # Relevance scoring and ranking
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_search_service.py
│   ├── test_fetch_service.py
│   ├── test_clean_service.py
│   ├── test_chunk_service.py
│   └── test_rank_service.py
│
├── .env.example
├── .env
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

### Phase 2+ (Full Structure)

```
hybrid-search-agents/
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── middleware/
│   │   │   ├── auth.py            # API key auth middleware
│   │   │   ├── rate_limit.py      # Request rate limiting
│   │   │   └── logging.py         # Structured request logging
│   │   └── routes/
│   │       ├── search.py
│   │       ├── health.py
│   │       ├── cache.py           # Cache management endpoints
│   │       └── admin.py           # Admin/monitoring endpoints
│   │
│   ├── models/
│   │   ├── request.py
│   │   ├── response.py
│   │   └── db/                    # SQLAlchemy DB models
│   │       ├── base.py
│   │       ├── query.py           # StoredQuery model
│   │       └── result.py          # StoredResult model
│   │
│   ├── services/
│   │   ├── search_service.py
│   │   ├── fetch_service.py
│   │   ├── clean_service.py
│   │   ├── chunk_service.py
│   │   ├── rank_service.py
│   │   ├── embed_service.py       # Embedding generation
│   │   ├── cache_service.py       # Redis caching
│   │   ├── store_service.py       # PostgreSQL persistence
│   │   ├── credibility_service.py # Source credibility scoring
│   │   └── citation_service.py    # Citation generation
│   │
│   ├── db/
│   │   ├── session.py             # Async DB session
│   │   └── migrations/            # Alembic migrations
│   │       ├── env.py
│   │       └── versions/
│   │
│   └── utils/
│       ├── text.py                # Text utilities
│       ├── url.py                 # URL utilities
│       └── retry.py               # Retry logic
│
├── mcp/
│   ├── __init__.py
│   ├── server.py                  # MCP server entry point
│   └── tools/
│       ├── search_tool.py         # Search tool definition
│       └── fetch_tool.py          # Fetch tool definition
│
├── frontend/                      # Next.js dashboard (Phase 6)
│   ├── src/
│   └── package.json
│
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── docker-compose.yml
│
├── scripts/
│   ├── seed_db.py
│   └── benchmark.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 6. API Design

### Base URL
```
http://localhost:8000/api/v1
```

### Endpoints

---

#### `GET /health`
Health check endpoint.

**Response**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2025-01-15T12:00:00Z"
}
```

---

#### `POST /search`
Main search endpoint. Accepts a query and returns structured, ranked content.

**Request Body**
```json
{
  "query": "how does vector search work in RAG systems",
  "max_results": 5,
  "max_chars_per_page": 8000,
  "chunk_size": 500,
  "chunk_overlap": 50,
  "min_score": 0.1
}
```

**Request Schema**

| Field | Type | Default | Description |
|---|---|---|---|
| query | string | required | The search query |
| max_results | int | 5 | Max number of web results to fetch |
| max_chars_per_page | int | 8000 | Max characters to extract per page |
| chunk_size | int | 500 | Target character length per chunk |
| chunk_overlap | int | 50 | Character overlap between chunks |
| min_score | float | 0.0 | Minimum relevance score (0.0–1.0) |

**Response Body**
```json
{
  "query": "how does vector search work in RAG systems",
  "total_results": 4,
  "processing_time_ms": 1842,
  "results": [
    {
      "rank": 1,
      "title": "Vector Search Explained — Pinecone",
      "url": "https://www.pinecone.io/learn/vector-search/",
      "content": "Vector search works by converting text into high-dimensional numerical representations called embeddings...",
      "chunks": [
        {
          "chunk_id": 0,
          "text": "Vector search works by converting text into high-dimensional numerical representations called embeddings. These embeddings capture semantic meaning...",
          "char_count": 487
        },
        {
          "chunk_id": 1,
          "text": "In a RAG system, when a user submits a query, it is embedded using the same model used to embed the document corpus...",
          "char_count": 501
        }
      ],
      "score": 0.87,
      "char_count": 4231,
      "chunk_count": 9
    }
  ]
}
```

**Response Schema**

| Field | Type | Description |
|---|---|---|
| query | string | Original query echoed back |
| total_results | int | Number of results returned |
| processing_time_ms | int | End-to-end latency |
| results | array | Ranked list of results |
| results[].rank | int | 1-based ranking position |
| results[].title | string | Page title |
| results[].url | string | Source URL |
| results[].content | string | Cleaned, trimmed full text |
| results[].chunks | array | RAG-ready text chunks |
| results[].chunks[].chunk_id | int | Zero-based chunk index |
| results[].chunks[].text | string | Chunk text content |
| results[].chunks[].char_count | int | Chunk character length |
| results[].score | float | Relevance score (0.0–1.0) |
| results[].char_count | int | Total content character count |
| results[].chunk_count | int | Total number of chunks |

**Error Responses**

```json
// 400 Bad Request
{
  "detail": "Query must be between 3 and 500 characters"
}

// 422 Unprocessable Entity
{
  "detail": [
    {
      "loc": ["body", "max_results"],
      "msg": "ensure this value is less than or equal to 10",
      "type": "value_error.number.not_le"
    }
  ]
}

// 503 Service Unavailable
{
  "detail": "Search service temporarily unavailable"
}
```

---

#### `GET /cache/status` *(Phase 2)*
Returns cache hit statistics.

#### `DELETE /cache/flush` *(Phase 2)*
Flushes the query cache.

#### `POST /search/semantic` *(Phase 3)*
Semantic search using vector embeddings against stored results.

#### `GET /mcp/tools` *(Phase 4)*
Lists available MCP tools.

---

## 7. Core Module Design

### 7.1 SearchService — `services/search_service.py`

Responsible for querying DuckDuckGo and returning a list of candidate URLs with metadata.

```python
from duckduckgo_search import DDGS
from app.models.response import SearchCandidate

class SearchService:
    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    async def search(self, query: str) -> list[SearchCandidate]:
        """
        Query DuckDuckGo and return top URL candidates.
        Returns list of {title, url, snippet} dicts.
        Filters out non-HTTP URLs and known non-content domains.
        """
        results = []
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=self.max_results * 2)
            for r in raw:
                if self._is_valid_url(r.get("href", "")):
                    results.append(SearchCandidate(
                        title=r.get("title", ""),
                        url=r["href"],
                        snippet=r.get("body", "")
                    ))
                if len(results) >= self.max_results:
                    break
        return results

    def _is_valid_url(self, url: str) -> bool:
        blocked = ["youtube.com", "reddit.com/r/", "twitter.com", "x.com"]
        return url.startswith("http") and not any(b in url for b in blocked)
```

**Key design choices:**
- Fetch 2× the required results to allow filtering
- Block multimedia/social URLs that won't contain useful text
- Return typed Pydantic candidates, not raw dicts

---

### 7.2 FetchService — `services/fetch_service.py`

Fetches clean markdown from each URL concurrently using Tinyfish Fetch API and httpx.

```python
import httpx
import asyncio

TINYFISH_ENDPOINT = "https://r.jina.ai/{url}"  
# Tinyfish/Jina Reader: prepend URL to get clean markdown

class FetchService:
    def __init__(self, timeout: int = 15, max_concurrent: int = 5):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_all(
        self,
        candidates: list[SearchCandidate],
        max_chars: int = 8000
    ) -> list[FetchedPage]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = [
                self._fetch_one(client, c, max_chars)
                for c in candidates
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, FetchedPage)]

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        candidate: SearchCandidate,
        max_chars: int
    ) -> FetchedPage | None:
        async with self.semaphore:
            try:
                url = TINYFISH_ENDPOINT.format(url=candidate.url)
                response = await client.get(
                    url,
                    headers={"Accept": "text/plain", "X-Return-Format": "markdown"}
                )
                response.raise_for_status()
                content = response.text[:max_chars]
                return FetchedPage(
                    title=candidate.title,
                    url=candidate.url,
                    raw_content=content
                )
            except Exception:
                return None  # Silently skip failed fetches
```

**Key design choices:**
- Semaphore limits concurrent requests to avoid rate limiting
- `asyncio.gather` with `return_exceptions=True` prevents one failure from killing the batch
- Content truncated at `max_chars` before further processing
- Failed fetches return `None` and are filtered out gracefully

---

### 7.3 CleanService — `services/clean_service.py`

Cleans raw markdown into dense, coherent text suitable for chunking.

```python
import re
import unicodedata

class CleanService:
    def clean(self, raw: str) -> str:
        text = self._normalize_unicode(raw)
        text = self._remove_markdown_noise(text)
        text = self._collapse_whitespace(text)
        text = self._remove_boilerplate(text)
        return text.strip()

    def _normalize_unicode(self, text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    def _remove_markdown_noise(self, text: str) -> str:
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)   # images
        text = re.sub(r"\[.*?\]\(.*?\)", r"\1", text) # links → anchor text
        text = re.sub(r"#{1,6}\s+", "", text)          # headers
        text = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.DOTALL)  # code
        text = re.sub(r"[*_~]{1,2}(.*?)[*_~]{1,2}", r"\1", text)     # bold/italic
        text = re.sub(r"^\s*[-*|>]\s+", "", text, flags=re.MULTILINE) # bullets/tables
        return text

    def _collapse_whitespace(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)  # max 2 blank lines
        text = re.sub(r" {2,}", " ", text)       # collapse spaces
        return text

    def _remove_boilerplate(self, text: str) -> str:
        boilerplate = [
            r"cookie policy.*", r"accept all cookies.*",
            r"subscribe to.*newsletter.*", r"all rights reserved.*",
            r"©\s*\d{4}.*",
        ]
        for pattern in boilerplate:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text
```

**Key design choices:**
- Pure Python, no heavy NLP deps in MVP
- Removes markdown syntax artifacts from Tinyfish output
- Collapses excessive whitespace for clean chunking
- Strips common boilerplate patterns

---

### 7.4 ChunkService — `services/chunk_service.py`

Splits cleaned content into overlapping chunks optimized for RAG.

```python
from app.models.response import ContentChunk

class ChunkService:
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[ContentChunk]:
        """
        Paragraph-aware chunking: respects paragraph boundaries
        where possible, falls back to character-level sliding window.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        chunk_id = 0

        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.chunk_size:
                current = f"{current}\n\n{para}".strip()
            else:
                if current:
                    chunks.append(ContentChunk(
                        chunk_id=chunk_id,
                        text=current,
                        char_count=len(current)
                    ))
                    chunk_id += 1
                    # Overlap: carry last N chars into next chunk
                    current = current[-self.overlap:] + "\n\n" + para
                    current = current.strip()
                else:
                    current = para

        if current:
            chunks.append(ContentChunk(
                chunk_id=chunk_id,
                text=current,
                char_count=len(current)
            ))

        return chunks
```

**Key design choices:**
- Paragraph-aware splitting preserves semantic boundaries
- Overlap ensures context is not lost at chunk boundaries
- Each chunk carries its own metadata for downstream use
- Returns typed `ContentChunk` objects

---

### 7.5 RankService — `services/rank_service.py`

Scores and ranks results by relevance to the original query using keyword-based heuristics in MVP.

```python
import math
from collections import Counter

class RankService:
    def rank(
        self,
        query: str,
        results: list[ProcessedResult]
    ) -> list[ProcessedResult]:
        query_terms = self._tokenize(query)
        for result in results:
            result.score = self._score(query_terms, result)
        return sorted(results, key=lambda r: r.score, reverse=True)

    def _score(self, query_terms: list[str], result: ProcessedResult) -> float:
        content_lower = result.content.lower()
        title_lower = result.title.lower()
        scores = []

        # Term frequency in content
        content_tokens = self._tokenize(content_lower)
        token_counts = Counter(content_tokens)
        total_tokens = len(content_tokens) or 1

        tf_scores = []
        for term in query_terms:
            tf = token_counts.get(term, 0) / total_tokens
            idf = math.log(1 + 1 / (1 + token_counts.get(term, 0)))
            tf_scores.append(tf * idf)
        content_score = sum(tf_scores) / len(query_terms) if query_terms else 0

        # Title match bonus
        title_hits = sum(1 for t in query_terms if t in title_lower)
        title_score = title_hits / len(query_terms) if query_terms else 0

        # Content density bonus (more content = more relevant)
        density_score = min(len(result.content) / 5000, 1.0) * 0.1

        final = (content_score * 0.6) + (title_score * 0.3) + density_score
        return round(min(final, 1.0), 4)

    def _tokenize(self, text: str) -> list[str]:
        return [w.lower() for w in text.split() if len(w) > 2]
```

**Key design choices:**
- TF-IDF variant without needing a corpus (self-contained scoring)
- Title match weighted heavily (0.3) since it's a strong signal
- Content density bonus rewards richer sources
- Score normalized to 0.0–1.0 range
- Easily replaceable with embedding cosine similarity in Phase 3

---

## 8. Data Flow & Pipeline

```
User Query: "how does vector search work in RAG systems"
       │
       ▼
[SearchService]
  DuckDuckGo DDGS → 10 raw results → filter to 5 valid URLs
  Output: [SearchCandidate(title, url, snippet), ...]
       │
       ▼
[FetchService]
  Concurrent httpx calls → Tinyfish Fetch API (r.jina.ai)
  5 concurrent requests, 15s timeout, semaphore-limited
  Output: [FetchedPage(title, url, raw_content), ...]
       │
       ▼
[CleanService]
  For each page: normalize → strip markdown → collapse whitespace → remove boilerplate
  Output: [CleanedPage(title, url, content), ...]
       │
       ▼
[ChunkService]
  For each page: paragraph-aware chunking with overlap
  Output: adds chunks: [[ContentChunk(id, text, chars), ...], ...]
       │
       ▼
[RankService]
  Score each result against query terms (TF-IDF + title match + density)
  Sort descending by score
  Output: [ProcessedResult(rank, title, url, content, chunks, score), ...]
       │
       ▼
JSON Response → Client/Agent
```

### Timing Breakdown (Expected)
- DuckDuckGo search: ~300–600ms
- Tinyfish concurrent fetch (5 URLs): ~800–1500ms (bottleneck)
- Cleaning + Chunking + Ranking: ~10–30ms
- **Total: ~1.2–2.5 seconds**

---

## 9. Phase 1 — MVP (Working Prototype)

### Goal
A fully working FastAPI application that takes a query and returns ranked, chunked, clean web content. Deployable locally with `uvicorn`.

### Implementation Steps

#### Step 1: Project Scaffolding (30 min)

```bash
mkdir hybrid-search-agents && cd hybrid-search-agents
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn httpx duckduckgo-search pydantic-settings python-dotenv
```

Create `pyproject.toml`:
```toml
[project]
name = "hybrid-search-agents"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "httpx>=0.27.0",
    "duckduckgo-search>=5.0.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.3.0",
]
```

#### Step 2: Configuration (15 min)

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Hybrid Search for Agents"
    version: str = "0.1.0"
    debug: bool = False

    # Search
    max_search_results: int = 5
    max_chars_per_page: int = 8000
    fetch_timeout_seconds: int = 15
    max_concurrent_fetches: int = 5

    # Chunking
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50

    # Tinyfish/Jina Fetch
    fetch_base_url: str = "https://r.jina.ai"

    class Config:
        env_file = ".env"

settings = Settings()
```

#### Step 3: Pydantic Models (20 min)

```python
# app/models/request.py
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    max_results: int = Field(default=5, ge=1, le=10)
    max_chars_per_page: int = Field(default=8000, ge=500, le=50000)
    chunk_size: int = Field(default=500, ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=200)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
```

```python
# app/models/response.py
from pydantic import BaseModel

class SearchCandidate(BaseModel):
    title: str
    url: str
    snippet: str = ""

class FetchedPage(BaseModel):
    title: str
    url: str
    raw_content: str

class ContentChunk(BaseModel):
    chunk_id: int
    text: str
    char_count: int

class SearchResult(BaseModel):
    rank: int
    title: str
    url: str
    content: str
    chunks: list[ContentChunk]
    score: float
    char_count: int
    chunk_count: int

class SearchResponse(BaseModel):
    query: str
    total_results: int
    processing_time_ms: int
    results: list[SearchResult]
```

#### Step 4: Implement All Services

Implement SearchService, FetchService, CleanService, ChunkService, RankService as designed in Section 7.

#### Step 5: API Route (20 min)

```python
# app/api/routes/search.py
import time
from fastapi import APIRouter, HTTPException
from app.models.request import SearchRequest
from app.models.response import SearchResponse, SearchResult
from app.services.search_service import SearchService
from app.services.fetch_service import FetchService
from app.services.clean_service import CleanService
from app.services.chunk_service import ChunkService
from app.services.rank_service import RankService

router = APIRouter(prefix="/search", tags=["search"])

@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest):
    start = time.monotonic()
    try:
        # 1. Search
        search_svc = SearchService(max_results=request.max_results)
        candidates = await search_svc.search(request.query)

        if not candidates:
            raise HTTPException(status_code=404, detail="No results found")

        # 2. Fetch
        fetch_svc = FetchService()
        fetched = await fetch_svc.fetch_all(candidates, request.max_chars_per_page)

        # 3. Clean + Chunk
        clean_svc = CleanService()
        chunk_svc = ChunkService(request.chunk_size, request.chunk_overlap)

        processed = []
        for page in fetched:
            cleaned = clean_svc.clean(page.raw_content)
            if not cleaned:
                continue
            chunks = chunk_svc.chunk(cleaned)
            processed.append({
                "title": page.title,
                "url": page.url,
                "content": cleaned,
                "chunks": chunks,
                "score": 0.0,
            })

        # 4. Rank
        rank_svc = RankService()
        ranked = rank_svc.rank(request.query, processed)

        # 5. Filter and format
        results = [
            SearchResult(
                rank=i + 1,
                title=r["title"],
                url=r["url"],
                content=r["content"],
                chunks=r["chunks"],
                score=r["score"],
                char_count=len(r["content"]),
                chunk_count=len(r["chunks"]),
            )
            for i, r in enumerate(ranked)
            if r["score"] >= request.min_score
        ]

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return SearchResponse(
            query=request.query,
            total_results=len(results),
            processing_time_ms=elapsed_ms,
            results=results,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Search failed: {str(e)}")
```

#### Step 6: FastAPI App Factory (10 min)

```python
# app/main.py
from fastapi import FastAPI
from app.config import settings
from app.api.routes import search, health

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    return app

app = create_app()
```

#### Step 7: Run & Test

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how does pgvector work", "max_results": 3}'
```

**Deliverable:** A locally running FastAPI server that returns clean, chunked, ranked web content for any query. ~2–3 days of focused development.

---

## 10. Phase 2 — Storage & Caching Layer

### Goal
Persist query results to PostgreSQL and add Redis caching to avoid redundant fetches for repeated queries. Cut repeat-query latency from ~2s to ~20ms.

### New Dependencies
```
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
alembic>=1.13.0
redis[asyncio]>=5.0.0
```

### Redis Cache Strategy

```python
# app/services/cache_service.py
import json
import hashlib
import redis.asyncio as aioredis
from app.config import settings

class CacheService:
    def __init__(self):
        self.client = aioredis.from_url(settings.redis_url)
        self.ttl = settings.cache_ttl_seconds  # default: 3600

    def _cache_key(self, query: str, params: dict) -> str:
        raw = f"{query}:{json.dumps(params, sort_keys=True)}"
        return f"search:{hashlib.sha256(raw.encode()).hexdigest()}"

    async def get(self, key: str) -> dict | None:
        data = await self.client.get(key)
        return json.loads(data) if data else None

    async def set(self, key: str, value: dict) -> None:
        await self.client.setex(key, self.ttl, json.dumps(value))
```

Cache keys are SHA-256 hashes of `(query + params)`. This ensures different parameter combinations (different chunk sizes, etc.) are cached separately.

### PostgreSQL Schema

```sql
-- queries table
CREATE TABLE queries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text  TEXT NOT NULL,
    query_hash  VARCHAR(64) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    result_count INT,
    processing_ms INT
);
CREATE INDEX idx_queries_hash ON queries(query_hash);

-- results table
CREATE TABLE results (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id    UUID REFERENCES queries(id) ON DELETE CASCADE,
    rank        INT NOT NULL,
    title       TEXT,
    url         TEXT NOT NULL,
    content     TEXT,
    score       FLOAT,
    char_count  INT,
    chunk_count INT,
    fetched_at  TIMESTAMPTZ DEFAULT NOW()
);

-- chunks table
CREATE TABLE chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id   UUID REFERENCES results(id) ON DELETE CASCADE,
    chunk_id    INT NOT NULL,
    text        TEXT NOT NULL,
    char_count  INT,
    embedding   VECTOR(1536)  -- Phase 3: pgvector column
);
```

### Updated Search Flow (Phase 2)

```
Query arrives →
  Check Redis cache (cache hit? → return immediately, ~20ms) →
  Cache miss: run full pipeline →
    Store results in PostgreSQL →
    Write to Redis with TTL →
  Return results
```

**Deliverable:** Redis caching (1-hour TTL) + PostgreSQL persistence. Cache hit responses in <50ms. Historical query analytics. ~3–5 days of development.

---

## 11. Phase 3 — Semantic Search & Embeddings

### Goal
Add vector embedding of chunks, store in pgvector, and enable semantic similarity search that retrieves relevant content even when keyword match is low.

### New Dependencies
```
openai>=1.0.0        # or: sentence-transformers for local embeddings
pgvector>=0.2.0
numpy>=1.26.0
```

### Embedding Strategy

**Option A — OpenAI API (hosted, highest quality)**
```python
from openai import AsyncOpenAI

class EmbedService:
    def __init__(self):
        self.client = AsyncOpenAI()
        self.model = "text-embedding-3-small"  # 1536 dims, cheap

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.model, input=texts
        )
        return [r.embedding for r in response.data]
```

**Option B — Local BGE Embeddings (free, private)**
```python
from sentence_transformers import SentenceTransformer

class EmbedService:
    def __init__(self):
        self.model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        # 384 dims, runs on CPU, ~80ms/batch

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()
```

Recommendation: Start with OpenAI for MVP quality, switch to BGE for cost/privacy when volume increases.

### pgvector Similarity Search

```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Find semantically similar chunks to a query embedding
SELECT
    c.text,
    r.title,
    r.url,
    1 - (c.embedding <=> $1) AS similarity
FROM chunks c
JOIN results r ON c.result_id = r.id
WHERE 1 - (c.embedding <=> $1) > 0.7
ORDER BY c.embedding <=> $1
LIMIT 10;
```

### New `/search/semantic` Endpoint

```
POST /api/v1/search/semantic
{
  "query": "similarity search cosine distance",
  "top_k": 10,
  "min_similarity": 0.7,
  "use_cache": true
}
```

This searches the existing chunk database by vector similarity — no new web fetches needed for stored topics.

### Hybrid Scoring (Combining Keyword + Semantic)

```python
final_score = (keyword_score * 0.4) + (semantic_score * 0.6)
```

Weights are configurable. Semantic score dominates once embeddings are available.

**Deliverable:** Chunk embeddings stored in pgvector. Semantic search endpoint. Hybrid scoring. ~5–7 days of development.

---

## 12. Phase 4 — Agent & MCP Integration

### Goal
Expose the retrieval system as an MCP (Model Context Protocol) server so any MCP-compatible AI agent (Claude, Cursor, etc.) can call it as a native tool.

### MCP Architecture

```
AI Agent (Claude / GPT / etc.)
      │  MCP JSON-RPC calls
      ▼
MCP Server (FastMCP)
      │  Internal HTTP
      ▼
Hybrid Search FastAPI Backend
      │
      ▼
Search → Fetch → Clean → Chunk → Rank → Return
```

### MCP Tool Definition

```python
# mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Hybrid Search for Agents")

@mcp.tool()
async def web_search(
    query: str,
    max_results: int = 5,
    chunk_size: int = 500,
) -> str:
    """
    Search the web and return clean, chunked, ranked content
    suitable for AI agent grounding and RAG pipelines.

    Args:
        query: The search query
        max_results: Number of web pages to retrieve (1-10)
        chunk_size: Target character size for each text chunk

    Returns:
        JSON string with ranked results including title, URL,
        content chunks, and relevance scores
    """
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/search",
            json={"query": query, "max_results": max_results, "chunk_size": chunk_size}
        )
        return response.text

if __name__ == "__main__":
    mcp.run()
```

### Claude Desktop MCP Config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "hybrid-search": {
      "command": "python",
      "args": ["-m", "mcp.server"],
      "cwd": "/path/to/hybrid-search-agents"
    }
  }
}
```

### OpenAI / Anthropic Function Calling Adapter

```python
# For direct API integration (not MCP)
SEARCH_TOOL_SCHEMA = {
    "name": "web_search",
    "description": "Search the web and return clean, chunked content for grounding AI responses",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
}
```

**Deliverable:** A working MCP server. Can be added to Claude Desktop. Any MCP-compatible agent can call hybrid search as a native tool. ~3–4 days of development.

---

## 13. Phase 5 — Production Hardening

### API Authentication

```python
# app/api/middleware/auth.py
from fastapi import Security, HTTPException
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(key: str = Security(api_key_header)):
    if key not in settings.valid_api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key
```

### Rate Limiting

```python
# Using slowapi (wraps limits library)
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("")
@limiter.limit("20/minute")
async def search(request: Request, body: SearchRequest):
    ...
```

### Source Credibility Scoring

```python
# app/services/credibility_service.py
TRUSTED_DOMAINS = {
    "arxiv.org": 0.95, "github.com": 0.9, "docs.python.org": 0.95,
    "wikipedia.org": 0.8, "stackoverflow.com": 0.85, "medium.com": 0.6,
    "reddit.com": 0.5, "quora.com": 0.45,
}

class CredibilityService:
    def score(self, url: str) -> float:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        return TRUSTED_DOMAINS.get(domain, 0.5)
```

Credibility score is combined with relevance score: `final = (relevance * 0.7) + (credibility * 0.3)`

### Citation Generation

```python
# app/services/citation_service.py
from datetime import date

class CitationService:
    def generate_apa(self, result: SearchResult) -> str:
        today = date.today().strftime("%Y, %B %d")
        title = result.title or result.url
        return f"{title}. Retrieved {today}, from {result.url}"

    def generate_markdown(self, results: list[SearchResult]) -> str:
        lines = ["## Sources\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r.title}]({r.url}) — Score: {r.score:.2f}")
        return "\n".join(lines)
```

### Structured Logging

```python
# Use structlog for JSON-formatted production logs
import structlog

logger = structlog.get_logger()

logger.info(
    "search_completed",
    query=request.query,
    results=len(results),
    elapsed_ms=elapsed_ms,
    cache_hit=False,
)
```

### Docker Setup

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```yaml
# docker-compose.yml
version: "3.9"
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:password@db/hybriddb
      - REDIS_URL=redis://cache:6379
    depends_on: [db, cache]

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: hybriddb
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    volumes: ["pgdata:/var/lib/postgresql/data"]

  cache:
    image: redis:7-alpine
    volumes: ["redisdata:/data"]

volumes:
  pgdata:
  redisdata:
```

**Deliverable:** Auth, rate limiting, credibility scoring, citation generation, Docker Compose setup, structured logging. Production-ready API. ~1 week of development.

---

## 14. Phase 6 — Frontend Dashboard

### Goal
A web dashboard for manual search, result inspection, cache management, and analytics.

### Tech: Next.js 14 + TypeScript + Tailwind

### Pages & Components

```
/                     → Search page (main query input + results)
/history              → Past queries with timestamps and result counts
/cache                → Cache management (view keys, flush)
/analytics            → Query volume, avg latency, top queries charts
/settings             → API key management, default parameters
```

### Search Result Component

```tsx
// components/SearchResult.tsx
interface Result {
  rank: number;
  title: string;
  url: string;
  content: string;
  chunks: { chunk_id: number; text: string }[];
  score: number;
}

export function SearchResultCard({ result }: { result: Result }) {
  return (
    <div className="border rounded-lg p-4 mb-4 shadow-sm">
      <div className="flex justify-between items-start">
        <div>
          <span className="text-sm text-gray-500">#{result.rank}</span>
          <h3 className="font-semibold text-blue-700">
            <a href={result.url} target="_blank">{result.title}</a>
          </h3>
          <p className="text-xs text-gray-400">{result.url}</p>
        </div>
        <span className="bg-green-100 text-green-800 text-sm px-2 py-1 rounded">
          {(result.score * 100).toFixed(0)}%
        </span>
      </div>
      <p className="mt-2 text-sm text-gray-700 line-clamp-3">{result.content}</p>
      <details className="mt-2">
        <summary className="text-xs text-gray-500 cursor-pointer">
          {result.chunks.length} chunks
        </summary>
        <div className="mt-1 space-y-1">
          {result.chunks.map(c => (
            <p key={c.chunk_id} className="text-xs bg-gray-50 p-2 rounded">
              {c.text}
            </p>
          ))}
        </div>
      </details>
    </div>
  );
}
```

**Deliverable:** Full dashboard for human-readable search, analytics, and cache management. ~1–2 weeks of development.

---

## 15. Deployment Strategy

### Development (Phase 1)
```bash
uvicorn app.main:app --reload
```

### Staging (Phase 2+)
```bash
docker-compose up --build
```

### Production Options

| Option | Best For | Cost |
|---|---|---|
| Railway | Fast deploys, Postgres included | ~$5–20/month |
| Render | Simple Docker deploys | ~$7–25/month |
| Fly.io | Global edge, good free tier | ~$0–20/month |
| AWS ECS | High scale, full control | Variable |
| Kubernetes | Enterprise multi-region | Variable |

### Recommended Starter Stack (Production)
- **App Server:** Fly.io (2 shared CPU, 512MB RAM) + auto-scaling
- **Database:** Supabase (PostgreSQL + pgvector built-in)
- **Cache:** Upstash Redis (serverless, pay-per-use)
- **Monitoring:** Better Stack (logs + uptime)
- **CI/CD:** GitHub Actions → Fly.io deploy

---

## 16. Security Considerations

| Concern | Mitigation |
|---|---|
| API abuse | API key authentication + rate limiting |
| SSRF via URL fetching | All fetches go through Tinyfish (external service) |
| SQL injection | SQLAlchemy parameterized queries (ORM) |
| Sensitive query logging | Hash queries in logs, not plaintext |
| DuckDuckGo ToS | Respect rate limits; add jitter between requests |
| Content injection | Content is returned as plain text/JSON, not rendered |
| Secrets management | `.env` local, environment vars in production, never in code |

---

## 17. Testing Strategy

### Unit Tests
Test each service in isolation with mocked dependencies.

```python
# tests/test_clean_service.py
from app.services.clean_service import CleanService

def test_removes_markdown_headers():
    svc = CleanService()
    result = svc.clean("## Hello World\nSome content here.")
    assert "##" not in result
    assert "Hello World" in result

def test_collapses_whitespace():
    svc = CleanService()
    result = svc.clean("Line one\n\n\n\nLine two")
    assert "\n\n\n" not in result
```

```python
# tests/test_chunk_service.py
from app.services.chunk_service import ChunkService

def test_chunks_respect_size():
    svc = ChunkService(chunk_size=100, overlap=10)
    text = "word " * 200  # 1000 chars
    chunks = svc.chunk(text)
    for chunk in chunks:
        assert chunk.char_count <= 200  # some tolerance for overlap

def test_chunk_overlap():
    svc = ChunkService(chunk_size=50, overlap=10)
    chunks = svc.chunk("A" * 200)
    assert len(chunks) > 1
```

### Integration Tests

```python
# tests/test_search_endpoint.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_search_returns_results():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "Python async programming", "max_results": 2}
        )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert data["total_results"] >= 0
```

### Test Coverage Targets

| Service | Target Coverage |
|---|---|
| CleanService | 95% |
| ChunkService | 95% |
| RankService | 90% |
| FetchService | 80% (mock httpx) |
| SearchService | 75% (mock DDGS) |
| API Routes | 85% |

Run with: `pytest --cov=app --cov-report=html -v`

---

## 18. Performance & Scaling

### Phase 1 Bottleneck
Network I/O from Tinyfish fetches dominates. Target: 5 concurrent fetches, ~2s total.

### Phase 2+ Optimizations

| Optimization | Impact | Complexity |
|---|---|---|
| Redis cache (1hr TTL) | Repeat queries: 2000ms → 20ms | Low |
| Increase concurrent fetches (5→10) | Reduce fetch time ~30% | Low |
| Pre-warm cache for trending queries | Near-zero latency for common topics | Medium |
| Connection pooling for PostgreSQL | Reduce DB overhead | Low |
| Uvicorn workers (4+) | Handle more concurrent requests | Low |
| CDN for static API responses | Edge caching for public queries | Medium |

### Load Targets

| Phase | Requests/min | Strategy |
|---|---|---|
| Phase 1 | 10 | Single process |
| Phase 2 | 60 | Redis cache + 4 workers |
| Phase 3 | 300 | + Connection pooling |
| Phase 5+ | 1000+ | Horizontal scaling, load balancer |

---

## 19. Roadmap Summary

```
PHASE 1 — MVP (Week 1–2)
├── FastAPI backend
├── DuckDuckGo search integration
├── Tinyfish fetch (async concurrent)
├── Text cleaning pipeline
├── Paragraph-aware chunking
├── TF-IDF keyword relevance ranking
└── Structured JSON response

PHASE 2 — Storage & Cache (Week 3–4)
├── PostgreSQL schema + SQLAlchemy ORM
├── Alembic migrations
├── Redis caching with SHA-256 keys
└── Query history persistence

PHASE 3 — Semantic Search (Week 5–7)
├── Chunk embedding (OpenAI or BGE)
├── pgvector storage + indexing
├── Semantic search endpoint
└── Hybrid keyword + semantic scoring

PHASE 4 — Agent Integration (Week 8–9)
├── MCP server (FastMCP)
├── Claude Desktop tool registration
├── OpenAI/Anthropic function calling schema
└── Agent-optimized response format

PHASE 5 — Production Hardening (Week 10–12)
├── API key authentication
├── Rate limiting (slowapi)
├── Source credibility scoring
├── Citation generation
├── Structured logging (structlog)
├── Docker Compose + production Dockerfile
└── Monitoring & alerts

PHASE 6 — Frontend Dashboard (Week 13–16)
├── Next.js search interface
├── Result inspector with chunk viewer
├── Query history + analytics
├── Cache management UI
└── API key management
```

---

*Document version 1.0 — Hybrid Search for Agents Project Blueprint*
*Last updated: 2025*
