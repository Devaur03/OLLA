# OLLA — Hybrid Search. Smarter Answers.

**A local-first web retrieval engine that returns a cited, LLM-synthesized answer — not a wall of blue links.**

You ask a question. OLLA searches the web, fetches and cleans the content, ranks
it, embeds it into a growing knowledge graph, asks a local LLM to write a direct
answer with inline `[n]` citations, and hands the whole thing back in one call —
with a per-stage trace so you can see exactly what happened.

```bash
# Zero to first answer:
git clone <your-repo-url> olla
cd olla
make setup && make migrate && make dev

# Ask something:
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how does pgvector work"}'
```

Three ways to drive it: the **HTTP API**, the **OLLA CLI** (`python cli.py`), and
the **web console** (`frontend/`). It also speaks **MCP**, so Claude Desktop can
call it as a native tool.

---

## Table of Contents

- [What OLLA Does](#what-olla-does)
- [The Pipeline](#the-pipeline)
- [Architecture](#architecture)
- [Setup](#setup)
  - [Backend — Docker](#backend--docker-compose)
  - [Backend — Local](#backend--local-development)
  - [Web console (frontend)](#web-console-frontend)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [The OLLA CLI](#the-olla-cli)
- [The Web Console](#the-web-console)
- [Knowledge Graph](#knowledge-graph)
- [Feedback & Learning](#feedback--learning)
- [MCP Integration](#mcp-integration)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)

---

## What OLLA Does

Given a natural-language query, OLLA:

1. **Searches** the web (DuckDuckGo, multi-backend with fallback) for candidate URLs.
2. **Fetches** clean content for each URL through a fetch waterfall (Jina Reader → direct scrape → snippet).
3. **Cleans, sanitizes and chunks** the text — strips boilerplate, removes prompt-injection attempts, splits into RAG-ready chunks.
4. **Ranks** results with TF-IDF + content density, then blends in a learned **source-trust** score.
5. **Synthesizes an answer** — a local LLM (via Ollama) reads the ranked sources and writes a direct answer with inline `[n]` citations.
6. **Stores** the query, results and chunks in PostgreSQL.
7. **Embeds** the new chunks locally (384-dim BGE vectors — no API key needed).
8. **Builds the knowledge graph** — links chunks by semantic similarity so OLLA's memory expands with every search.

Every stage is wrapped in a trace span (`success` / `fallback` / `skipped` / `failed`)
returned on the response and persisted for the dashboard. Non-fatal stages can fail
without taking down the request — the response is just marked `degraded`.

On top of the core pipeline OLLA adds **confidence-routed hybrid retrieval**
(cache → local memory → fresh web crawl), **knowledge-graph traversal**,
**feedback-driven ranking**, **API-key auth**, and **MCP**.

**Stack:** FastAPI · PostgreSQL + pgvector · Redis · `BAAI/bge-small-en-v1.5`
(local embeddings) · Ollama (local answer LLM) · React + Vite frontend · Docker Compose.

---

## The Pipeline

![OLLA Pipeline](docs/images/pipeline.png)

`search` and `fetch` are **critical** — if they fail the request fails. The
enrichment stages (`store`, `embed`, `graph`) are **non-fatal**: a failure there
marks the response `degraded` but still returns results and an answer.

---

## Architecture

![OLLA Architecture](docs/images/diagramarch.png)

---

## Setup

### Backend — Docker Compose

The fastest path. Brings up the API, PostgreSQL (pgvector) and Redis together.

```bash
cp .env.example .env          # adjust if you like
make docker-up                # build + start api, db, cache
make migrate                  # run Alembic migrations (inside the api container)
```

Or directly:

```bash
cd docker
docker-compose up --build -d
docker-compose exec api alembic upgrade head
```

The API is then at `http://localhost:8000` · interactive docs at `/docs`.

### Backend — Local Development

```bash
# 1. virtualenv + dependencies
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. PostgreSQL (pgvector) + Redis — easiest via Docker
make docker-up                         # starts just db + cache, or use your own

# 3. configure + migrate
cp .env.example .env
make migrate                           # alembic upgrade head

# 4. run the API
make dev                               # uvicorn app.main:app --reload
```

**Local answer synthesis (optional but recommended).** OLLA writes its answers
with a local LLM through [Ollama](https://ollama.com). Without it, searches still
return ranked sources — just no synthesized answer.

```bash
ollama serve
ollama pull qwen2.5:1.5b               # small + fast; set OLLAMA_MODEL in .env
```

Verify the LLM wiring any time with `python cli.py --test-llm`.

### Web console (frontend)

A React + Vite single-page console that drives every API feature.

```bash
cd frontend
npm install
npm run dev          # dev server on http://localhost:5173 (proxies /api → :8000)
npm run build        # production build → frontend/dist/
```

The dev server proxies `/api/*` to `http://127.0.0.1:8000`, so just keep the
backend running alongside it.

---

## Environment Variables

Copy `.env.example` to `.env`. The most relevant settings:

```bash
# ── Core ─────────────────────────────────────────────────────────
DEBUG=false

# ── Search & fetch ───────────────────────────────────────────────
MAX_SEARCH_RESULTS=5
MAX_CHARS_PER_PAGE=8000
FETCH_TIMEOUT_SECONDS=15
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50

# ── PostgreSQL ───────────────────────────────────────────────────
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5433/hybriddb"

# ── Redis ────────────────────────────────────────────────────────
REDIS_URL="redis://localhost:6379"
CACHE_TTL_SECONDS=3600

# ── Embeddings (local by default — no API key needed) ────────────
USE_LOCAL_EMBEDDINGS=true
OPENAI_API_KEY=""                      # only if USE_LOCAL_EMBEDDINGS=false

# ── Knowledge graph ──────────────────────────────────────────────
ENABLE_KNOWLEDGE_GRAPH=true            # embed + graph stages on every search
GRAPH_SIMILARITY_THRESHOLD=0.85        # min cosine similarity to draw an edge

# ── Answer synthesis (local LLM via Ollama) ──────────────────────
ENABLE_ANSWER_SYNTHESIS=true
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="qwen2.5:1.5b"

# ── Auth ─────────────────────────────────────────────────────────
REQUIRE_AUTH=false
API_KEYS="key1,key2"                   # comma-separated; used when REQUIRE_AUTH=true
```

> **Privacy mode:** set `LOCAL_ONLY=true` to forbid any request from reaching an
> external AI provider — local embeddings are forced and external keys cleared.

---

## API Reference

All endpoints are under `/api/v1`. Interactive docs at `/docs`.

### `GET /api/v1/health`
Deep health check — overall status plus per-component status and latency
(database, cache, …). Always returns 200, exempt from auth.

### `POST /api/v1/search`
The main pipeline. Body:

| Field | Type | Default | Notes |
|---|---|---|---|
| `query` | string | required | 3–500 chars |
| `max_results` | int | 5 | 1–10 — pages to fetch |
| `max_chars_per_page` | int | 8000 | per-page character cap |
| `chunk_size` | int | 500 | target chars per chunk |
| `chunk_overlap` | int | 50 | overlap between chunks |
| `min_score` | float | 0.0 | minimum score to keep a result |
| `llm_model` | string | — | override the Ollama answer model |

Returns a `SearchResponse`:

```json
{
  "query": "how does pgvector work",
  "total_results": 5,
  "processing_time_ms": 2140,
  "results": [
    { "rank": 1, "title": "...", "url": "...", "content": "...",
      "score": 0.91, "chunks": [ ... ] }
  ],
  "answer": "pgvector stores embeddings as a native column type [1] ...",
  "answer_model": "qwen2.5:1.5b",
  "trace": [ { "stage": "search", "status": "success", "duration_ms": 410, "detail": "..." }, ... ],
  "degraded": false,
  "cache_hit": false,
  "query_id": "f1e2…",
  "citations_markdown": "...",
  "citations_json": [ ... ]
}
```

> `query_id` is the UUID of the stored query — pass it back as `query_id` when
> submitting answer-level feedback.

### `POST /api/v1/search/hybrid`
Confidence-routed retrieval: checks cache and local semantic memory first, and
only crawls the web when memory confidence is low or the query is recency-sensitive.

| Field | Type | Default | Notes |
|---|---|---|---|
| `query` | string | required | |
| `mode` | string | `auto` | `auto` · `fast` · `fresh` · `hybrid` · `deep` |
| `max_results` | int | 6 | |

The response includes `retrieval_mode`, `query_class`, `confidence`,
`from_memory`, and a human-readable `routing_trace`.

### `POST /api/v1/search/graph`
Knowledge-graph traversal. Finds seed chunks by vector similarity to the query,
then walks `chunk_edges` outward. Body: `{ query, hops, seed_k, top_k }`.
Returns `seed_chunks`, `connected_chunks`, `total_chunks`, `hops`.

### `POST /api/v1/search/semantic`
Pure vector similarity over stored chunks. Body: `{ query, top_k, min_similarity }`.

### `POST /api/v1/search/embed-and-store`
Backfills embeddings for any stored chunks that don't have one yet. With the
knowledge graph enabled this runs automatically on every search, so it's mostly
a manual catch-up tool.

### `POST /api/v1/feedback`
Records feedback and updates ranking signals. Body:

| Field | Type | Notes |
|---|---|---|
| `level` | string | `answer` · `citation` · `chunk` · `source` |
| `feedback_type` | string | `useful` · `not_useful` · `incorrect` · `outdated` · `bad_source` · `missing_context` |
| `query_id` | string | required for `answer`-level feedback |
| `source_url` | string | required for `source`/`citation`-level feedback |
| `chunk_id` | string | required for `chunk`-level feedback |
| `comment` | string | optional free-text note |

### `GET /api/v1/feedback/stats`
Aggregate analytics — totals, satisfaction rate, top/low-trust sources.

### `POST /api/v1/register`
Public — register an email and receive a free-tier API key (shown once).

### `GET` / `POST` / `DELETE /api/v1/keys`
List, create and revoke API keys (authenticated).

---

## The OLLA CLI

`cli.py` is a polished terminal client. Run it with no arguments for the
interactive shell, or pass a query for one-shot mode.

```bash
python cli.py                          # interactive OLLA shell
python cli.py "how does pgvector work" # one-shot search
python cli.py "latest AI news" --hybrid --mode fresh
python cli.py "vector similarity" --graph
python cli.py --health
python cli.py --test-llm               # diagnose the local Ollama LLM
python cli.py --feedback-stats
```

### Interactive shell

`python cli.py` opens a welcome banner (OLLA wordmark, getting-started panel,
live API status) and a prompt. Just type a question to search, or use a command:

| Command | Action |
|---|---|
| `<your question>` / `/ask <q>` | search and get a synthesized answer |
| `/hybrid on\|off` | toggle confidence-routed hybrid retrieval |
| `/mode <name>` | hybrid mode: `auto` `fast` `fresh` `hybrid` `deep` |
| `/graph <query>` | explore the knowledge graph |
| `/feedback` | rate the last answer **or one of its sources** |
| `/health` | API health + components |
| `/llm` | diagnose the local Ollama LLM |
| `/stats` | feedback analytics |
| `/max <n>` · `/sources on\|off` · `/json on\|off` | tune output |
| `/host` · `/ollama` · `/model` | point at different hosts/models |
| `/set` | show current settings |
| `/help` · `/clear` · `/exit` | — |

One-shot flags include `--host`, `--max`, `--graph`, `--hybrid`, `--mode`,
`--json`, `--no-sources`, `--health`, `--test-llm`, `--ollama`, `--model`,
`--feedback` (with `--level` / `--type`), and `--feedback-stats`.

The CLI uses `rich` for its terminal UI — installed with the other requirements.

---

## The Web Console

`frontend/` is a React + Vite single-page app, themed to match the CLI
(dark, monospace, cyan→violet). It has a hero section and a tabbed console where
every tab calls the real API:

- **Search** — cited answer, sources, animated pipeline trace.
- **Hybrid** — mode selector + routing/confidence metadata.
- **Graph** — seed chunks and connected (hop) context.
- **Health** — live per-component status.
- **Feedback** — rate the last answer or a specific source it used.
- **Analytics** — satisfaction gauge, feedback-by-type, source trust.
- **Keys** — mint a free-tier API key.

Run `npm run dev` in `frontend/` with the backend up; build with `npm run build`.

> A legacy self-contained dashboard is also served by the backend at `/dashboard`.

---

## Knowledge Graph

When `ENABLE_KNOWLEDGE_GRAPH=true` (the default), every search runs two extra
pipeline stages after `store`:

- **embed** — vectorises the chunks just stored (local BGE model, cached in-process).
- **graph** — `GraphService.build_edges()` draws `chunk_edges` between chunks whose
  cosine similarity is at or above `GRAPH_SIMILARITY_THRESHOLD`.

So the graph grows continuously: each search both contributes new content and
links it to everything already stored. `POST /api/v1/search/graph` then does
multi-hop traversal — seed by similarity, walk the edges — to surface connected
context that plain vector search would miss.

---

## Feedback & Learning

Feedback is first-class. You can rate four things — the synthesized **answer**,
a **citation**, a retrieved **chunk**, or a **source** domain — via
`POST /api/v1/feedback`, the CLI's `/feedback`, or the console's Feedback tab.

Source-level feedback feeds the **source-trust** score, which the ranking stage
blends into result scoring (`final = relevance × 0.7 + source_trust × 0.3`), so
results measurably improve as feedback accumulates. `GET /api/v1/feedback/stats`
exposes the aggregate picture.

---

## MCP Integration

`mcp_server/server.py` exposes OLLA as a Model Context Protocol tool over stdio,
so Claude Desktop can call web search as a native tool. Add to
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "olla": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/olla"
    }
  }
}
```

The FastAPI server must be running on port 8000 before Claude Desktop starts it.

---

## Project Structure

```
olla/
├── cli.py                     ← OLLA CLI (interactive shell + one-shot)
├── app/
│   ├── main.py                ← FastAPI app factory, middleware, routers
│   ├── config.py              ← Pydantic settings (all env vars)
│   ├── api/
│   │   ├── middleware/        ← auth · rate-limit · tracing · usage-meter
│   │   └── routes/            ← health · search · semantic · hybrid · graph ·
│   │                             feedback · keys · sources · workspaces · …
│   ├── models/
│   │   ├── request.py         ← request schemas
│   │   ├── response.py        ← response schemas
│   │   └── db/                ← SQLAlchemy ORM models (query, result, chunk,
│   │                             chunk_edge, feedback, source_trust, …)
│   ├── services/
│   │   ├── pipeline.py        ← staged, traced search orchestrator
│   │   ├── retrieval_router.py← confidence-routed hybrid retrieval
│   │   ├── search_service.py  · fetch_service.py · clean_service.py
│   │   ├── chunk_service.py   · rank_service.py  · answer_service.py
│   │   ├── embed_service.py   · graph_service.py · store_service.py
│   │   ├── feedback_service.py· source_trust_service.py
│   │   ├── cache_service.py   · citation_service.py · …
│   └── db/
│       ├── session.py         ← async engine + session factory
│       └── migrations/        ← Alembic (001 … 008)
├── mcp_server/server.py       ← MCP stdio server
├── frontend/                  ← React + Vite web console
│   ├── index.html
│   └── src/  (App.tsx, App.css, index.css, main.tsx)
├── docker/                    ← Dockerfile + docker-compose.yml
├── eval/                      ← retrieval-quality benchmark harness
├── tests/                     ← pytest suite
├── Makefile · alembic.ini · requirements.txt · pyproject.toml
└── .env.example
```

---

## Running Tests

```bash
make test            # full pytest suite
make test-fast       # unit tests only (no network / DB)
make test-coverage   # with a coverage report
make smoke           # quick end-to-end smoke check
make lint            # ruff
make fmt             # ruff format
```

Or call `pytest` directly, e.g. `pytest tests/ -v`.

---

## Troubleshooting

**No synthesized answer in results / `answer` is empty.**
The local LLM isn't reachable. Start Ollama (`ollama serve`) and pull the model
(`ollama pull qwen2.5:1.5b`). Diagnose with `python cli.py --test-llm`. Search
and sources still work without it — only the synthesized answer needs Ollama.

**`graph` stage shows `skipped`.**
The graph builds only when chunks have embeddings. Confirm
`ENABLE_KNOWLEDGE_GRAPH=true` and that `sentence-transformers` is installed; the
first embed loads the BGE model (~130 MB download, one time).

**First search is very slow.**
The local embedding model loads on first use. It's cached in-process afterwards,
so subsequent searches are fast.

**`asyncpg … UndefinedTableError`.**
Migrations haven't run — `make migrate` (or `alembic upgrade head`).

**`redis … ConnectionError`.**
Redis isn't running or `REDIS_URL` is wrong. Start it (`make docker-up`).

**`422 Unprocessable Entity` on `/search`.**
The body failed validation — most often a `query` shorter than 3 characters.

**Frontend can't reach the API.**
Run the backend on port 8000 and use the Vite dev server (`npm run dev`), which
proxies `/api` to it. A production build (`dist/`) needs its own reverse proxy
for `/api`.

**Cannot connect to `localhost` / proxy issues.**
An `HTTP_PROXY` / `ALL_PROXY` env var can black-hole localhost requests. The CLI
already disables proxies for its calls; for other clients, unset those vars.

---

*OLLA — Hybrid Search. Smarter Answers.*
