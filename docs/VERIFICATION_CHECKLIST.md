# End-to-End Verification Checklist

> Work through this in order. Each step has a command, the expected result, and
> what to do if it fails. Do not skip ahead — later steps depend on earlier ones.
> When every box is ticked, the project is demo-ready.

Paths assume the repo root `C:\1DevG\ddgsSearch`. Commands are shown for
PowerShell; adjust quoting for other shells.

---

## Step 0 — Backing services

The app needs PostgreSQL (with pgvector), Redis, and Ollama. The `.env` file
points at `localhost:5433` for Postgres, `localhost:6379` for Redis,
`localhost:11434` for Ollama — match those or edit `.env`.

- [ ] **PostgreSQL + pgvector**
  ```
  docker run -d --name hybrid-db -e POSTGRES_DB=hybriddb ^
    -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=password ^
    -p 5433:5432 pgvector/pgvector:pg16
  ```
- [ ] **Redis**
  ```
  docker run -d --name hybrid-cache -p 6379:6379 redis:7-alpine
  ```
- [ ] **Ollama** — install the Ollama app, then pull the model:
  ```
  ollama pull llama3.2:1b
  ```
  Verify: `curl http://localhost:11434/api/tags` lists the model.

If you skip Ollama, everything still works **except** the synthesized answer —
searches return results with an empty `answer` field. That is expected, not a bug.

---

## Step 1 — Python dependencies

- [ ] Install deps into a virtualenv:
  ```
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```
- [ ] Confirm it imports cleanly:
  ```
  python -c "import app.main"
  ```
  **Expected:** no output, no traceback.
  **If it fails:** a `ModuleNotFoundError` means a missing package — `pip install`
  it. An `ImportError` from `app.*` means a code bug — note the file and line.

---

## Step 2 — Database migrations

This is the step most likely to surface a problem, because migrations 005–008
have never been run.

- [ ] Apply all migrations:
  ```
  alembic upgrade head
  ```
  **Expected:** a line per migration up to `Running upgrade 007 -> 008`.
- [ ] Confirm the head:
  ```
  alembic current
  ```
  **Expected:** `008 (head)`.
- [ ] Spot-check the schema — connect to the DB and run:
  ```
  \d feedback
  \d source_trust
  SELECT * FROM workspaces;
  ```
  **Expected:** `feedback` and `chunks` have a `workspace_id` column;
  `source_trust` has a composite primary key `(workspace_id, domain)`;
  the `workspaces` table has one row — the Default workspace
  `00000000-0000-0000-0000-000000000000`.

**If a migration fails partway:** note which revision. `alembic downgrade -1`
backs out the last one. A migration that half-applied may need a manual fix
before re-running.

---

## Step 3 — Backend boots + health

- [ ] Start the API (apply the auth-middleware fix first — just restart):
  ```
  uvicorn app.main:app --reload --port 8000
  ```
  **Expected:** startup log lines, no traceback. The log should mention
  `auth=`, `embeddings=`, etc.
- [ ] Health check:
  ```
  curl http://localhost:8000/api/v1/health
  ```
  **Expected:** `{"status": ...}` with a `components` block. Each component
  (`database`, `redis`, ...) should read `ok`. A `slow` or `error` here points
  straight at the misconfigured service.
- [ ] Open `http://localhost:8000/docs` — the Swagger page should list every
  route group: search, semantic, hybrid, feedback, graph, sources, admin,
  workspaces, keys, billing, health.

---

## Step 4 — Web search + LLM answer

- [ ] Run a search:
  ```
  curl -X POST http://localhost:8000/api/v1/search ^
    -H "Content-Type: application/json" ^
    -d "{\"query\": \"how does pgvector work\", \"max_results\": 3}"
  ```
  **Expected:** JSON with `results` (1–3 items, each with title/url/content/
  score), `citations_markdown`, `total_results > 0`, and `degraded: false`.
  If Ollama is running, `answer` is a non-empty paragraph with `[1]`-style
  citations and `answer_model` is set.
- [ ] **Check `degraded`** — if `true`, inspect the `trace` array: each stage
  has a `status`. A `failed` stage tells you exactly what broke. The `store`
  stage failing means a DB problem (most likely migrations not fully applied).
- [ ] **If `answer` is empty** but results are present: Ollama is down or the
  model isn't pulled. Run `python cli.py --test-llm` to diagnose.

---

## Step 5 — Persistence check

- [ ] After Step 4, query the database:
  ```
  SELECT count(*) FROM queries;
  SELECT count(*) FROM results;
  SELECT count(*) FROM chunks;
  SELECT DISTINCT workspace_id FROM results;
  ```
  **Expected:** non-zero counts, and `workspace_id` is
  `00000000-0000-0000-0000-000000000000` (the Default workspace) — **not NULL**.
  A NULL here means the auth-middleware fix did not take effect; restart the
  server.

---

## Step 6 — Embeddings backfill

Semantic and hybrid search need embeddings. New chunks are stored without them.

- [ ] Generate embeddings for stored chunks:
  ```
  curl -X POST http://localhost:8000/api/v1/search/embed-and-store
  ```
  **Expected:** `{"message": "Embedding complete", "processed": N}` with `N > 0`.
  First run downloads the BGE model (~130 MB) — it will be slow once.
- [ ] Confirm: `SELECT count(*) FROM chunks WHERE embedding IS NOT NULL;` — `> 0`.

---

## Step 7 — Semantic search

- [ ] Query stored vectors:
  ```
  curl -X POST http://localhost:8000/api/v1/search/semantic ^
    -H "Content-Type: application/json" ^
    -d "{\"query\": \"vector similarity\", \"top_k\": 5}"
  ```
  **Expected:** `chunks` array with `similarity` scores, `total_chunks > 0`.
  **If `total_chunks` is 0:** either Step 6 produced no embeddings, or the
  query genuinely matches nothing — try a query close to content you searched
  in Step 4.

---

## Step 8 — Hybrid retrieval

- [ ] Run the router:
  ```
  curl -X POST http://localhost:8000/api/v1/search/hybrid ^
    -H "Content-Type: application/json" ^
    -d "{\"query\": \"what is a vector database\", \"mode\": \"auto\"}"
  ```
  **Expected:** JSON with `retrieval_mode`, `query_class`, `confidence`,
  `from_memory`, and a `routing_trace` array explaining each decision.
- [ ] Run the **same query again** — `routing_trace` should show a cache hit or
  a memory hit (`from_memory: true`) and a much lower `processing_time_ms`.
- [ ] Try a recency query (`"latest AI news"`) — `query_class` should be `news`
  or `recent` and it should crawl the web (`from_memory: false`).

---

## Step 9 — Feedback loop + insights

- [ ] Submit feedback (source-level needs only a URL):
  ```
  curl -X POST http://localhost:8000/api/v1/feedback ^
    -H "Content-Type: application/json" ^
    -d "{\"level\": \"source\", \"feedback_type\": \"useful\", ^
         \"source_url\": \"https://github.com/pgvector/pgvector\"}"
  ```
  **Expected:** `{"recorded": true, "effects": [...]}`. The `effects` list
  should mention recording the event and adjusting learned trust.
- [ ] Read the analytics:
  ```
  curl http://localhost:8000/api/v1/feedback/stats
  ```
  **Expected:** `total >= 1`, the feedback type shows under `by_type`, and the
  domain appears in `best_sources`. **If `total` is 0 after submitting** —
  the workspace fix did not take; recheck Step 5.

---

## Step 10 — Sources + admin endpoints

- [ ] `GET /api/v1/sources/recent-queries` — lists the queries from Steps 4/8.
- [ ] `GET /api/v1/sources/trusted-domains` — lists the domain from Step 9.
- [ ] `GET /api/v1/sources/{result_id}` — pick a `result_id`
  (`SELECT id FROM results LIMIT 1;`) — returns the result and its chunks.
- [ ] `GET /api/v1/admin/retention/stats` — returns row counts.
- [ ] `GET /api/v1/admin/export` — returns a JSON dump with `sources`,
  `feedback`, `source_trust`, `queries` sections.

---

## Step 11 — Frontend

The React changes (feedback buttons, Insights tab) have never been built.

- [ ] Build it:
  ```
  cd frontend
  npm install
  npm run build
  ```
  **Expected:** a clean build into `frontend/dist`. **A TypeScript error here
  is plausible** — note the file/line; it will be a type mismatch to fix.
- [ ] Restart the API (it serves `frontend/dist`) and open
  `http://localhost:8000/`. Walk through:
  - [ ] Search tab — run a query, results render.
  - [ ] Each result card shows **Useful / Not useful / Outdated** buttons;
        clicking one shows "✓ Thanks".
  - [ ] **Feedback insights** tab — shows total feedback, satisfaction %, and
        the source-trust rankings from Step 9.
  - [ ] API Key registry and Billing tabs still load.

---

## Step 12 — CLI

- [ ] `python cli.py "how does pgvector work"` — prints an answer + sources.
- [ ] `python cli.py "what is RAG" --hybrid` — shows retrieval mode +
      confidence + routing trace.
- [ ] `python cli.py --feedback-stats` — shows the analytics table.
- [ ] `python cli.py --health` — shows component health.

---

## Step 13 — MCP server (optional, for the agent demo)

- [ ] With the API running, start the MCP server:
  ```
  python -m mcp_server.server
  ```
  **Expected:** log lines listing 8 tools and 3 resources, no traceback.
- [ ] Wire it into Claude Desktop (`claude_desktop_config.json`) and confirm a
      tool call (e.g. `hybrid_search`) returns results.

---

## Step 14 — Evaluation harness (optional, for the numbers)

- [ ] With the API running and some data stored:
  ```
  python -m eval.run_eval --limit 5
  ```
  **Expected:** progress lines, then a summary (latency speedup, memory-served
  rate) and `eval/benchmark_report.md` written. Use this report's numbers in
  your write-up.

---

## Common failures — quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| `column "workspace_id" does not exist` | Migration 008 not applied | `alembic upgrade head` |
| Feedback/semantic return nothing | `workspace_id` resolving to NULL | Restart API (auth fix); recheck Step 5 |
| `answer` always empty | Ollama down / model not pulled | `ollama pull llama3.2:1b`; `cli.py --test-llm` |
| Search `degraded: true` | A non-fatal stage failed | Read the `trace` array for the failed stage |
| `redis.ConnectionError` | Redis not running | Start the Redis container |
| `asyncpg ... UndefinedTable` | Migrations not run | `alembic upgrade head` |
| `npm run build` TypeScript error | Frontend type mismatch | Fix the reported file/line |
| DuckDuckGo `RateLimitError` | Too many searches too fast | Wait, retry; it is intermittent |

---

## Definition of demo-ready

Every box above ticked, and specifically: a web search returns a cited answer,
semantic + hybrid search return results, feedback submitted in the UI appears
on the Insights tab, and the frontend builds and renders without console
errors. Until then, treat the project as "written but unverified".
