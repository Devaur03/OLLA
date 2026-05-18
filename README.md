# Hybrid Search for Agents

**Self-hosted web search + semantic retrieval backend for AI agents and RAG pipelines.**

Your AI agent asks a question. This system searches the web, fetches clean content, ranks it, stores it with vector embeddings, and returns structured results with citations — all in one API call. Works with Claude Desktop via MCP out of the box.

```bash
# Get from zero to first search result in under 5 minutes:
git clone https://github.com/YOUR_USERNAME/hybrid-search-agents.git
cd hybrid-search-agents
make setup && make migrate && make dev

# Then search:
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how does pgvector work"}'
```

Or open **http://localhost:8000/dashboard** in your browser.

---

**Why this exists:** Most RAG setups glue together 4–5 separate services manually. This gives you search → fetch → clean → chunk → rank → embed → cache as a single deployable stack with one `docker-compose up`.

**What you get:**
- `POST /api/v1/search` — web search with ranking and citations (1–3s first call, <50ms cached)
- `POST /api/v1/search/semantic` — vector similarity over your stored knowledge base
- `/dashboard` — web UI to search, inspect results, and monitor system health
- `hybrid-search "query"` — CLI for terminal-native access
- Claude Desktop integration via MCP (stdio)

**Stack:** FastAPI · PostgreSQL + pgvector · Redis · BAAI/bge-small-en-v1.5 (local, no API key) · Docker Compose

→ **[QUICKSTART.md](QUICKSTART.md)** — step-by-step from clone to first result
→ **[CONTRIBUTING.md](CONTRIBUTING.md)** — dev setup and contribution guide

---

## Table of Contents

- [What This System Does](#what-this-system-does)
- [Architecture Overview](#architecture-overview)
- [Complete Folder Structure](#complete-folder-structure)
- [Environment Variables Reference](#environment-variables-reference)
- [Phase 1 — Web Retrieval MVP](#phase-1--web-retrieval-mvp)
- [Phase 2A — PostgreSQL & Vector Storage](#phase-2a--postgresql--vector-storage)
- [Phase 2B — Redis Caching](#phase-2b--redis-caching)
- [Phase 3 — Local Embeddings & Semantic Search](#phase-3--local-embeddings--semantic-search)
- [Phase 4 — MCP Server](#phase-4--mcp-server)
- [Phase 5 — Production Docker Stack](#phase-5--production-docker-stack)
- [Bonus — Citation & Credibility Services](#bonus--citation--credibility-services)
- [API Reference](#api-reference)
- [Running the Project](#running-the-project)
- [Running Tests](#running-tests)
- [Verification Checklists](#verification-checklists)
- [Common Errors & Fixes](#common-errors--fixes)

---

## What This System Does

This project is a multi-phase web retrieval backend designed to feed high-quality, ranked, and semantically searchable content to AI agents. Given a natural-language query, the system:

1. Searches DuckDuckGo for the top candidate URLs.
2. Fetches clean markdown from each URL via the Jina Reader API (`r.jina.ai`).
3. Cleans and normalises the text, stripping boilerplate, images, and noise.
4. Splits content into overlapping chunks suitable for RAG pipelines.
5. Scores and ranks results using TF-IDF plus a content-density heuristic.
6. Adjusts scores using domain credibility weights (e.g. official docs rank higher than random blogs).
7. Persists queries, results, and chunks to PostgreSQL with pgvector support.
8. Caches identical queries in Redis for sub-50ms repeat responses.
9. Generates and stores 384-dimensional vector embeddings locally (no external embedding API required).
10. Serves semantic (cosine-similarity) search over stored chunks.
11. Exposes the whole pipeline as an MCP tool that Claude Desktop can call directly.
12. Returns structured citations in both Markdown and APA-JSON formats.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT / AI AGENT                     │
│           (curl, Claude Desktop via MCP, any HTTP client)    │
└─────────────────────┬───────────────────────────────────────┘
                       │  HTTP / stdio (MCP)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ /health │  │ /search  │  │/semantic │  │MCP server   │  │
│  └─────────┘  └────┬─────┘  └────┬─────┘  │(stdio wrap) │  │
│                    │              │        └─────────────┘  │
│  Auth Middleware ──┘              │                          │
│                                  │                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   SERVICE LAYER                       │   │
│  │  SearchService  →  FetchService  →  CleanService      │   │
│  │       ↓                                               │   │
│  │  ChunkService  →  RankService  →  CredibilityService  │   │
│  │       ↓                                               │   │
│  │  EmbedService    StoreService    CitationService       │   │
│  │       ↓               ↓                               │   │
│  │  CacheService    CacheService                         │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────┬────────────────────┬────────────────────────┘
               │                    │
               ▼                    ▼
┌──────────────────────┐   ┌────────────────────┐
│  PostgreSQL + pgvec  │   │       Redis         │
│  (queries, results,  │   │  (query result      │
│   chunks, embeddings)│   │   cache, TTL: 1hr)  │
└──────────────────────┘   └────────────────────┘
```

---

## Complete Folder Structure

```
hybrid-search-agents/
├── app/
│   ├── __init__.py
│   ├── main.py                         ← FastAPI app factory, middleware, routers
│   ├── config.py                       ← Pydantic Settings (all env vars)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                 ← API key auth (toggleable)
│   │   │   └── rate_limit.py           ← Request rate limiting
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py               ← GET /api/v1/health
│   │       ├── search.py               ← POST /api/v1/search (main pipeline)
│   │       └── semantic.py             ← POST /api/v1/search/semantic
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py                  ← SearchRequest, SemanticRequest Pydantic models
│   │   ├── response.py                 ← SearchResponse, ProcessedResult, ContentChunk
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── base.py                 ← SQLAlchemy DeclarativeBase
│   │       ├── query.py                ← ORM model: searches table
│   │       ├── result.py               ← ORM model: results table
│   │       └── chunk.py                ← ORM model: chunks table (includes Vector column)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── search_service.py           ← DuckDuckGo organic search
│   │   ├── fetch_service.py            ← Concurrent URL fetch via Jina Reader
│   │   ├── clean_service.py            ← Markdown cleaning & boilerplate removal
│   │   ├── chunk_service.py            ← Overlapping paragraph-aware chunking
│   │   ├── rank_service.py             ← TF-IDF + density scoring
│   │   ├── cache_service.py            ← Redis GET / SET / EXPIRE
│   │   ├── store_service.py            ← Async Postgres persistence
│   │   ├── embed_service.py            ← Local BGE embeddings (384-dim)
│   │   ├── credibility_service.py      ← Domain authority scoring (0.0–1.0)
│   │   └── citation_service.py         ← APA + Markdown citation generation
│   └── db/
│       ├── __init__.py
│       ├── session.py                  ← Async SQLAlchemy engine & session factory
│       └── migrations/
│           ├── env.py
│           ├── script.py.mako
│           └── versions/
│               ├── 001_initial.py      ← Creates queries, results, chunks tables
│               └── 002_add_vectors.py  ← Adds embedding column (pgvector)
├── mcp/
│   ├── __init__.py
│   └── server.py                       ← MCP stdio server exposing web_search tool
├── docker/
│   ├── Dockerfile                      ← Python 3.11-slim, CPU-only PyTorch
│   └── docker-compose.yml              ← api + db (pgvector:pg16) + cache (redis:7)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_clean_service.py
│   ├── test_chunk_service.py
│   ├── test_rank_service.py
│   ├── test_search_endpoint.py         ← Integration tests (requires internet)
│   ├── test_cache_service.py
│   ├── test_store_service.py
│   └── test_semantic_endpoint.py
├── .env.example
├── .env
├── pyproject.toml
└── requirements.txt                    ← Generated via pip freeze for Docker
```

---

## Environment Variables Reference

Copy `.env.example` to `.env` and fill in the values relevant to your setup. All phases are controlled through this single file.

```bash
# ── Core ────────────────────────────────────────────────────────
APP_NAME="Hybrid Search for Agents"
APP_VERSION="0.1.0"
DEBUG=false

# ── Search & Fetch (Phase 1) ────────────────────────────────────
MAX_SEARCH_RESULTS=5
MAX_CHARS_PER_PAGE=8000
FETCH_TIMEOUT_SECONDS=15
MAX_CONCURRENT_FETCHES=5
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50
FETCH_BASE_URL="https://r.jina.ai"

# ── PostgreSQL (Phase 2A) ───────────────────────────────────────
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/hybriddb"
DATABASE_ECHO=false

# ── Redis (Phase 2B) ────────────────────────────────────────────
REDIS_URL="redis://localhost:6379"
CACHE_TTL_SECONDS=3600

# ── Embeddings (Phase 3) ────────────────────────────────────────
# Set USE_LOCAL_EMBEDDINGS=true to use the local BGE model (no API key needed)
USE_LOCAL_EMBEDDINGS=true
OPENAI_API_KEY=""               # Only required if USE_LOCAL_EMBEDDINGS=false
EMBEDDING_MODEL="text-embedding-3-small"
EMBEDDING_DIMENSIONS=1536

# ── Auth (Phase 5) ──────────────────────────────────────────────
REQUIRE_AUTH=false
API_KEYS="key1,key2,key3"       # Comma-separated; ignored when REQUIRE_AUTH=false
```

---

## Phase 1 — Web Retrieval MVP

**Goal:** Build the core synchronous search → fetch → clean → chunk → rank pipeline and expose it as a single HTTP endpoint.

### How It Works

The request arrives at `POST /api/v1/search`. The route orchestrates five services in sequence:

`SearchService` queries DuckDuckGo via the `duckduckgo_search` library and returns a list of candidate URLs and titles. `FetchService` uses `httpx` to concurrently hit the Jina Reader proxy (`https://r.jina.ai/<url>`) for each URL, which returns clean markdown instead of raw HTML. `CleanService` strips images, collapses whitespace, removes code blocks and markdown headers, and produces dense plain text. `ChunkService` splits the text into overlapping pieces that respect paragraph boundaries — each chunk tracks its ID and character count. `RankService` scores every result against the original query using a TF-IDF heuristic augmented by a title-match bonus, then sorts descending.

### Key Files

`app/services/search_service.py` — wraps `duckduckgo_search.DDGS` to return a list of `{url, title}` dicts.

`app/services/fetch_service.py` — `asyncio.gather` over Jina Reader URLs; respects `MAX_CONCURRENT_FETCHES` and `FETCH_TIMEOUT_SECONDS`.

`app/services/clean_service.py` — regex-based cleaning pipeline; outputs dense text capped at `MAX_CHARS_PER_PAGE` characters.

`app/services/chunk_service.py` — paragraph-boundary-aware splitter with configurable `chunk_size` and `overlap`; returns a list of `ContentChunk` objects.

`app/services/rank_service.py` — normalised TF-IDF scoring; scores are always in `[0.0, 1.0]`.

`app/api/routes/search.py` — the main route; builds the pipeline and returns the `SearchResponse`.

### Output Shape

```json
{
  "query": "how does pgvector work",
  "total_results": 3,
  "processing_time_ms": 2140,
  "results": [
    {
      "rank": 1,
      "title": "pgvector: Open-source vector similarity search for Postgres",
      "url": "https://github.com/pgvector/pgvector",
      "content": "...",
      "chunks": [
        { "chunk_id": 0, "text": "...", "char_count": 487 }
      ],
      "score": 0.91
    }
  ]
}
```

---

## Phase 2A — PostgreSQL & Vector Storage

**Goal:** Persist every query, result, and chunk to PostgreSQL so that search history is available for analytics and subsequent semantic search.

### How It Works

On every cache miss, after the pipeline returns results, `StoreService` asynchronously inserts three related records: a row in the `queries` table (query text, timestamp, result count), one row per result in the `results` table (title, URL, score), and one row per chunk in the `chunks` table (text, char count, and — once Phase 3 runs — the embedding vector). Database failures are caught and logged but do NOT cause the search endpoint to return an error; the HTTP response is unaffected.

The database uses the `pgvector/pgvector:pg16` Docker image so the `vector` extension is available from day one. Alembic manages migrations.

### Key Files

`app/db/session.py` — creates the async SQLAlchemy engine with connection pooling (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`) and provides `get_db_session()` as a FastAPI dependency.

`app/models/db/query.py` — ORM model for the `queries` table; one-to-many with `results`.

`app/models/db/result.py` — ORM model for the `results` table; one-to-many with `chunks`.

`app/models/db/chunk.py` — ORM model for the `chunks` table; includes a `Vector(384)` column that is `NULL` until embeddings are generated.

`app/services/store_service.py` — wraps all three inserts in a single async transaction.

`app/db/migrations/versions/001_initial.py` — creates the tables and enables the `pgvector` extension.

### Setup Commands

```bash
# Start PostgreSQL with pgvector (if not using Docker Compose)
docker run -d \
  --name hybrid-search-db \
  -e POSTGRES_DB=hybriddb \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Run migrations
alembic upgrade head
```

---

## Phase 2B — Redis Caching

**Goal:** Short-circuit repeat queries so identical searches return in under 50ms without re-hitting DuckDuckGo or Jina.

### How It Works

At the very start of `POST /api/v1/search`, the route calls `CacheService.get(query)`. On a cache hit the serialised `SearchResponse` is returned immediately. On a miss the full pipeline runs, and before returning, `CacheService.set(query, response, ttl=CACHE_TTL_SECONDS)` stores the result. The default TTL is one hour.

Cache hits and misses are logged: `Cache HIT for 'query'` / `Cache MISS for 'query'`.

### Key Files

`app/services/cache_service.py` — connects to Redis; `get()` deserialises from JSON, `set()` serialises and calls `EXPIRE`. Exposes `ping()` for health checks.

`app/api/routes/search.py` — the cache check is the first and last step of the route handler.

### Performance

| Scenario | Typical Response Time |
|---|---|
| Cache miss (full pipeline, 5 results) | 1,500–3,000 ms |
| Cache hit | < 50 ms |

---

## Phase 3 — Local Embeddings & Semantic Search

**Goal:** Generate vector embeddings for stored chunks using a local model and expose a semantic search endpoint — no external embedding API required.

### How It Works

`EmbedService` downloads and caches `BAAI/bge-small-en-v1.5` from Hugging Face on first use. This model produces 384-dimensional float vectors. Two additional endpoints are added to the search router:

`POST /api/v1/search/embed-and-store` reads all chunks from the database that have a `NULL` embedding, generates embeddings in batches, and writes them back. This is run once after initial data ingestion, and then periodically as new data accumulates.

`POST /api/v1/search/semantic` accepts a query string, embeds it using the same local model, and performs a cosine-similarity search against all chunk embeddings stored in PostgreSQL via the `pgvector` `<=>` operator. Results are returned ordered by similarity score.

### Key Files

`app/services/embed_service.py` — loads the BGE model on startup; `embed(texts: list[str]) -> list[list[float]]` is the main interface.

`app/api/routes/semantic.py` — the `/semantic` route; handles query embedding and vector similarity query.

`app/db/migrations/versions/002_add_vectors.py` — adds the `embedding vector(384)` column to the `chunks` table and creates an IVFFlat index for efficient similarity search.

### Output Shape (Semantic Endpoint)

```json
[
  {
    "chunk_id": "uuid",
    "text": "pgvector stores embeddings as fixed-length float arrays ...",
    "similarity": 0.94,
    "result_title": "pgvector README",
    "result_url": "https://github.com/pgvector/pgvector"
  }
]
```

---

## Phase 4 — MCP Server

**Goal:** Expose the search pipeline as a Model Context Protocol (MCP) tool so that Claude Desktop and other MCP-compatible AI clients can call web search as a native tool.

### How It Works

`mcp/server.py` implements an MCP server that communicates over `stdio` (standard input/output), which is how Claude Desktop spawns and talks to local tool servers. The server registers a single tool named `web_search`. When an AI client calls it with a `query` argument, the MCP server makes an internal HTTP request to the running FastAPI instance on `localhost:8000` and forwards the structured response back to the client.

### Setup — Claude Desktop Config

Add the following to Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hybrid-search": {
      "command": "python",
      "args": ["-m", "mcp.server"],
      "cwd": "/absolute/path/to/hybrid-search-agents"
    }
  }
}
```

The FastAPI server must be running on port 8000 before Claude Desktop starts the MCP server.

### Key File

`mcp/server.py` — registers the `web_search` tool, validates arguments, calls `http://localhost:8000/api/v1/search`, and returns the MCP-formatted response.

---

## Phase 5 — Production Docker Stack

**Goal:** Containerise the entire stack for consistent, reproducible deployment.

### Services

Three containers are orchestrated by Docker Compose, each with health checks:

The `api` container runs the FastAPI application with 4 Uvicorn workers. It waits for both `db` and `cache` to pass their health checks before starting.

The `db` container runs `pgvector/pgvector:pg16`. Data is persisted to a named Docker volume (`pgdata`). Health is checked with `pg_isready`.

The `cache` container runs `redis:7-alpine` with `appendonly yes` for durability. Data is persisted to a named volume (`redisdata`). Health is checked with `redis-cli ping`.

### Auth Middleware

`app/api/middleware/auth.py` provides optional API key authentication. When `REQUIRE_AUTH=true` in the environment, every request must include an `X-API-Key` header whose value matches one of the comma-separated keys in `API_KEYS`. The `GET /api/v1/health` endpoint is always exempt from auth checks. When `REQUIRE_AUTH=false` (the default), all requests pass through without any key check.

### Key Files

`docker/Dockerfile` — `python:3.11-slim` base; installs CPU-only PyTorch to keep the image lean; runs `uvicorn` with 4 workers.

`docker/docker-compose.yml` — defines `api`, `db`, `cache` services with health checks, named volumes, and a shared network. Database and Redis URLs are injected as environment variables so no `.env` file needs to be inside the container.

### Deploy Commands

```bash
# Build and start all three services
cd docker
docker-compose up --build -d

# Run Alembic migrations inside the running api container
docker-compose exec api alembic upgrade head

# Tail application logs
docker-compose logs -f api

# Stop the stack
docker-compose down
```

---

## Bonus — Citation & Credibility Services

**Goal:** Improve result quality by weighting domain authority into the ranking score and enrich the API response with structured, ready-to-use citations.

### Credibility Service

`app/services/credibility_service.py` exposes a `score(domain: str) -> float` method. It maintains an internal dictionary of known high-authority domains (official documentation sites, peer-reviewed publishers, government domains, etc.) mapped to weights between `0.0` and `1.0`. Unknown domains fall back to a neutral baseline. The `RankService` calls this during the ranking step to adjust the TF-IDF score by the credibility multiplier, so a result from an official documentation site will outrank a structurally similar result from an unverified blog.

### Citation Service

`app/services/citation_service.py` receives the final ranked results and produces two citation formats for each:

`generate_apa(result)` returns an APA-style citation string with title, URL, and a programmatically generated access date.

`generate_markdown_link(result)` returns a Markdown-formatted hyperlink with relevance score and retrieved date.

`generate_citations_json(results)` returns a list of structured citation objects — one per result — containing rank, title, url, score, retrieved_date, the APA string, and the markdown link.

### Updated Response Shape

The final `SearchResponse` now includes two additional top-level fields:

```json
{
  "query": "...",
  "total_results": 3,
  "processing_time_ms": 2200,
  "results": [ ... ],
  "citations_markdown": "1. [pgvector README](https://github.com/pgvector/pgvector) — Score: 0.91 — Retrieved: 2025-06-15\n2. ...",
  "citations_json": [
    {
      "rank": 1,
      "title": "pgvector README",
      "url": "https://github.com/pgvector/pgvector",
      "score": 0.91,
      "retrieved_date": "2025-06-15",
      "apa": "pgvector README. Retrieved June 15, 2025, from https://github.com/pgvector/pgvector",
      "markdown": "[pgvector README](https://github.com/pgvector/pgvector)"
    }
  ]
}
```

---

## API Reference

### `GET /api/v1/health`

Returns service status. Always returns 200, even when auth is enabled.

```json
{ "status": "ok", "version": "0.1.0", "service": "Hybrid Search for Agents" }
```

### `POST /api/v1/search`

Main pipeline endpoint. Accepts a JSON body:

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `query` | string | required | 3–500 chars | The search query |
| `max_results` | int | 5 | 1–10 | Pages to fetch and process |
| `max_chars_per_page` | int | 8000 | 500–50000 | Character limit per page |
| `chunk_size` | int | 500 | 100–2000 | Target chars per chunk |
| `chunk_overlap` | int | 50 | 0–200 | Overlap between chunks |
| `min_score` | float | 0.0 | 0.0–1.0 | Minimum score threshold |

Returns a `SearchResponse` with `query`, `total_results`, `processing_time_ms`, `results[]`, `citations_markdown`, and `citations_json`.

### `POST /api/v1/search/embed-and-store`

Generates embeddings for all stored chunks that do not yet have one. Run after initial data ingestion.

```json
{ "message": "Processed 47 chunks", "processed": 47 }
```

### `POST /api/v1/search/semantic`

Finds the most similar stored chunks to a query using vector cosine similarity.

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Natural-language query to embed and search |
| `top_k` | int | 10 | Number of similar chunks to return |

Returns a list of chunks ordered by similarity score descending.

---

## Running the Project

### Option A — Local Development (no Docker)

```bash
# 1. Clone and set up a virtual environment
git clone <your-repo-url>
cd hybrid-search-agents
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start PostgreSQL and Redis (requires Docker for these two services)
docker run -d --name hybrid-search-db \
  -e POSTGRES_DB=hybriddb -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=password \
  -p 5432:5432 pgvector/pgvector:pg16

docker run -d --name hybrid-search-cache \
  -p 6379:6379 redis:7-alpine

# 4. Configure environment
cp .env.example .env
# Edit .env as needed

# 5. Run database migrations
alembic upgrade head

# 6. Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Option B — Full Docker Compose Stack

```bash
cd docker
docker-compose up --build -d
docker-compose exec api alembic upgrade head
```

The API will be available at `http://localhost:8000`. Interactive API docs are at `http://localhost:8000/docs`.

### Quick Smoke Test

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Run a search
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how does pgvector work for semantic search",
    "max_results": 3,
    "chunk_size": 400,
    "chunk_overlap": 40
  }'

# Semantic search (after running embed-and-store)
curl -X POST http://localhost:8000/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{ "query": "vector similarity cosine distance", "top_k": 5 }'
```

---

## Running Tests

```bash
# Unit tests only (no network or database required)
pytest tests/test_clean_service.py tests/test_chunk_service.py tests/test_rank_service.py -v

# Unit tests with coverage report
pytest tests/test_clean_service.py tests/test_chunk_service.py tests/test_rank_service.py \
  --cov=app/services --cov-report=term-missing -v

# Integration tests (requires internet connection and running API)
pytest tests/test_search_endpoint.py -v -s

# Full test suite (requires all services running)
pytest -v
```

---

## Verification Checklists

### Phase 1 — MVP
- [ ] `GET /api/v1/health` returns `{"status": "ok"}`
- [ ] `POST /api/v1/search` with a valid query returns a structured JSON response
- [ ] Response contains `query`, `total_results`, `processing_time_ms`, `results`
- [ ] Each result contains `rank`, `title`, `url`, `content`, `chunks`, `score`
- [ ] Results are sorted by score descending
- [ ] A query shorter than 3 characters returns HTTP 422
- [ ] `processing_time_ms` is under 5000 for a 3-result query
- [ ] Unit tests pass for `CleanService`, `ChunkService`, `RankService`
- [ ] Interactive docs render at `http://localhost:8000/docs`

### Phase 2A — PostgreSQL
- [ ] `alembic upgrade head` completes without errors
- [ ] After a search, rows exist in the `queries`, `results`, and `chunks` tables
- [ ] A database failure does not cause the search endpoint to return an error

### Phase 2B — Redis
- [ ] First search call: `processing_time_ms` is 1,500–3,000 ms
- [ ] Second identical search call: `processing_time_ms` is under 100 ms
- [ ] Logs show `Cache HIT` on the second call
- [ ] `CacheService.ping()` returns `True`

### Phase 3 — Embeddings
- [ ] `POST /api/v1/search/embed-and-store` runs without error after initial data exists
- [ ] `POST /api/v1/search/semantic` returns relevant chunks for a related query
- [ ] Semantic search returns no results (or low-scoring results) for a completely unrelated query
- [ ] Migration `002_add_vectors.py` applied: `chunks.embedding` column exists in the database

### Phase 4 — MCP
- [ ] `python -m mcp.server` starts without errors (FastAPI must be running on port 8000 first)
- [ ] Claude Desktop config updated with the correct `cwd` path
- [ ] Claude can call the `web_search` tool from within Claude Desktop and receive results

### Phase 5 — Production
- [ ] `docker-compose up` starts all three services without errors
- [ ] All Docker health checks pass (`docker-compose ps` shows `healthy` for all services)
- [ ] With `REQUIRE_AUTH=true` and valid `API_KEYS`, requests without a key return HTTP 403
- [ ] With `REQUIRE_AUTH=false`, all requests pass through without any key check
- [ ] `GET /api/v1/health` returns 200 even when auth is required

### Bonus — Citations & Credibility
- [ ] `SearchResponse` includes `citations_markdown` string
- [ ] `SearchResponse` includes `citations_json` list with one entry per result
- [ ] Each citation object has `rank`, `title`, `url`, `score`, `retrieved_date`, `apa`, `markdown`
- [ ] A result from a high-authority domain scores higher than a structurally equivalent result from an unknown domain

---

## Common Errors & Fixes

**`ModuleNotFoundError: No module named 'duckduckgo_search'`**
```bash
pip install "duckduckgo-search>=6.0.0"
```

**`RateLimitError` or `DuckDuckGoSearchException`**

DuckDuckGo throttles aggressive requests. Add a small delay in `SearchService.search()`:
```python
import asyncio
await asyncio.sleep(0.5)
```

**`httpx.ConnectError` on Jina fetch**

The Jina Reader API (`r.jina.ai`) is unreachable. Check your internet connection.

**`422 Unprocessable Entity` on `POST /search`**

The request body does not match the schema. The most common cause is a `query` shorter than 3 characters.

**`ImportError: cannot import name 'ProcessedResult'`**

Ensure `app/models/response.py` contains the `ProcessedResult` class as defined in Phase 1.

**`asyncpg.exceptions.UndefinedTableError`**

Alembic migrations have not been run. Execute `alembic upgrade head`.

**`redis.exceptions.ConnectionError`**

Redis is not running or `REDIS_URL` points to the wrong host. Start the Redis container and verify the URL in `.env`.

**Embeddings generate very slowly on first run**

The `BAAI/bge-small-en-v1.5` model is being downloaded from Hugging Face. This is a one-time download (~130 MB). Subsequent startups load it from local cache.

**`docker-compose up` fails with `port already in use`**

Another process is using port 5432, 6379, or 8000. Stop the conflicting process or change the host-side port mapping in `docker-compose.yml`.

---

## Dependencies Summary

| Package | Purpose | Phase Introduced |
|---|---|---|
| `fastapi` | Web framework | 1 |
| `uvicorn[standard]` | ASGI server | 1 |
| `httpx` | Async HTTP client for Jina fetch | 1 |
| `duckduckgo-search` | Organic search without an API key | 1 |
| `pydantic` / `pydantic-settings` | Data validation & settings management | 1 |
| `python-dotenv` | `.env` file loading | 1 |
| `sqlalchemy[asyncio]` | Async ORM | 2A |
| `asyncpg` | Async PostgreSQL driver | 2A |
| `alembic` | Database migrations | 2A |
| `redis` / `aioredis` | Redis client | 2B |
| `sentence-transformers` | Local BGE embedding model | 3 |
| `torch` (CPU) | PyTorch runtime for embeddings | 3 |
| `pgvector` | SQLAlchemy type for vector columns | 3 |
| `mcp` | Model Context Protocol SDK | 4 |

---

*End of final README — all phases complete.*
