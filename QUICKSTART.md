# Quickstart — Zero to First Search in 5 Minutes

**Prerequisites:** Docker Desktop running, Python 3.11+, Git.

---

## Step 1 — Clone and set up

```bash
git clone https://github.com/YOUR_USERNAME/hybrid-search-agents.git
cd hybrid-search-agents
make setup
```

`make setup` does three things: copies `.env.example` → `.env`, installs Python deps, and starts PostgreSQL + Redis in Docker.

---

## Step 2 — Create the database schema

```bash
make migrate
```

Expected output:
```
→ Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Add vectors
  ✓ Migrations applied
```

**Troubleshooting:** If you see `connection refused`, PostgreSQL is still starting. Wait 5 seconds and retry.

---

## Step 3 — Start the API server

```bash
make dev
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Starting OLLA v0.1.0
```

Open **http://localhost:8000/docs** in your browser — you'll see the interactive API docs.

---

## Step 4 — Run your first search

```bash
curl -s -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how does pgvector work", "max_results": 3}' \
  | python3 -m json.tool | head -60
```

Or open the dashboard at **http://localhost:8000/dashboard** and type a query there.

A successful response looks like:
```json
{
  "query": "how does pgvector work",
  "total_results": 3,
  "processing_time_ms": 2341,
  "results": [ ... ],
  "citations_markdown": "## Sources\n1. [pgvector docs](...)",
  "citations_json": [ ... ]
}
```

First call takes 1–3 seconds (fetching + ranking). Identical repeat calls return in **< 50ms** from Redis cache.

---

## Step 5 — Enable semantic search (optional)

Backfill embeddings for the results you just stored:

```bash
curl -s -X POST http://localhost:8000/api/v1/search/embed-and-store \
  | python3 -m json.tool
```

Then search semantically against your stored knowledge base:

```bash
curl -s -X POST http://localhost:8000/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{"query": "nearest neighbour index", "top_k": 5}' \
  | python3 -m json.tool
```

> Semantic search uses the local `BAAI/bge-small-en-v1.5` model by default — no OpenAI key needed.
> First call downloads the model (~130 MB). Subsequent calls are instant.

---

## Step 6 — Connect to Claude Desktop (optional)

Add this to your `claude_desktop_config.json` (find it at `~/Library/Application Support/Claude/` on Mac):

```json
{
  "mcpServers": {
    "hybrid-search": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/hybrid-search-agents"
    }
  }
}
```

Restart Claude Desktop. You can now say *"Search the web for how RAG pipelines work"* and Claude will call your local search server.

---

## Common issues

| Symptom | Fix |
|---|---|
| `connection refused` on port 5433 | PostgreSQL is still starting — wait 5s, retry |
| `connection refused` on port 6379 | Redis isn't running — run `make docker-up` |
| `ModuleNotFoundError` | Run `make setup` again to install deps |
| Empty results from search | DDG rate-limited — wait 30s and retry, or add a `BRAVE_API_KEY` in `.env` |
| Embeddings download stuck | First run downloads ~130MB model — let it finish |

---

## CLI alternative

```bash
# Install the CLI globally
pip install -e .

# Then from anywhere:
hybrid-search "what is retrieval augmented generation"
hybrid-search "pgvector cosine similarity" --top 5 --semantic
```

---

## What's running

| Service | URL | Purpose |
|---|---|---|
| API | http://localhost:8000 | Main FastAPI backend |
| Docs | http://localhost:8000/docs | Interactive API explorer |
| Dashboard | http://localhost:8000/dashboard | Web UI for search + health |
| PostgreSQL | localhost:5433 | Persistent storage + pgvector |
| Redis | localhost:6379 | Result cache (1hr TTL) |
