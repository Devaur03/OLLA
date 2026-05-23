# Remaining Features — 12-Phase Roadmap Status

> Gap analysis of the codebase against the 12-phase feature plan
> (MVP → advanced LinkedIn-worthy version). Last updated: 2026-05-23.

Status legend: ✅ done · 🟡 mostly · ❌ not started

---

## Snapshot

| Phase | Title | Status |
|---|---|---|
| 1 | Core Working MVP | ✅ done |
| 2 | Production-Ready RAG Stack | ✅ done |
| 3 | Local-First AI Layer | ✅ done |
| 4 | Vector DB + Semantic Memory | ✅ done |
| 5 | Hybrid Retrieval Router | ✅ done |
| 6 | Feedback Loop MVP | ✅ done |
| 7 | Feedback-Aware Ranking | ✅ done |
| 8 | MCP Agent Integration | ✅ done (8 tools + resources) |
| 9 | Dashboard, CLI, Developer Experience | 🟡 mostly (CLI + 2 UI features; SDK + 2 UI pages left) |
| 10 | Advanced Retrieval Quality | 🟡 mostly (deep-research multi-crawl left) |
| 11 | Observability and Evaluation | 🟡 mostly (metrics dashboard UI left) |
| 12 | Enterprise / SaaS-Ready Layer | 🟡 mostly (multi-tenant workspaces left) |

---

## What was built (Phases 5–12, this engagement)

### Phase 5 — Hybrid Retrieval Router
`POST /api/v1/search/hybrid`. `query_classifier_service` (news/recent/technical/
comparison/definition/research/evergreen), `freshness_service` (per-class
exponential decay), `retrieval_router` (cache → vector memory → web, with
confidence/freshness routing and FAST/FRESH/HYBRID/DEEP modes + `routing_trace`).

### Phase 6 — Feedback Loop
`POST /api/v1/feedback`, `GET /api/v1/feedback/stats`. Migration 005 (`feedback`,
`source_trust` tables; freshness columns on `results`; feedback columns on
`chunks`). `feedback_service` records verbatim and applies ranking effects —
metadata only, never rewrites scraped content.

### Phase 7 — Feedback-Aware Ranking
`source_trust_service` (learned per-domain trust blended 50/50 with static
credibility), `scoring_service` (the weighted formula). Feedback updates chunk
`usefulness_score`, domain `trust_score`, and `refresh_needed`. The web pipeline
and the router memory path both rank with these signals.

### Phase 8 — MCP Agent Integration
MCP server exposes eight tools (`web_search`, `semantic_search`, `hybrid_search`,
`submit_feedback`, `graph_search`, `feedback_stats`, `get_source`,
`refresh_source`) and three resources (`trusted-domains`, `recent-queries`,
`retrieval-stats`). `get_source` / `refresh_source` are backed by new
`/api/v1/sources/*` endpoints; the hybrid response already carries agent-safe
`confidence` / `retrieval_mode` fields.

### Phase 9 — CLI + UI
CLI: `--hybrid` / `--mode`, `--feedback`, `--feedback-stats`. React dashboard:
feedback buttons on every result card; a "Feedback insights" tab with
satisfaction rate, type breakdown, and source-trust rankings.

### Phase 10 — Advanced Retrieval Quality
`rerank_service` (optional cross-encoder, graceful passthrough),
`query_expansion_service` (rewrite + multi-query expand), `diversity_service`
(domain-spread guard), `citation_verifier_service` (verifies answer `[n]`
citations) — all wired into the router. Parent-child chunking
(`ChunkService.chunk_hierarchical`, migration 007, opt-in via
`ENABLE_PARENT_CHILD_CHUNKING`, stored by `store_service`).

### Phase 11 — Observability & Evaluation
`eval/` package: a categorized dataset, retrieval metrics (precision@k, nDCG@k,
MRR, citation support), and a runner that benchmarks web vs hybrid-cold vs
hybrid-warm and writes `eval/benchmark_report.md`.

### Phase 3 / 12 — Privacy, lifecycle, access
Privacy mode (`LOCAL_ONLY` / `DISABLE_EXTERNAL_LLM`), per-request `llm_model`
override. `/api/v1/admin/*`: retention purge + stats, export, import. Sliding-
window rate limiting middleware. RBAC — `role` on API keys (migration 006),
`require_role` dependency gating the admin routes.

**Tests:** 70+ unit tests added across query classification, freshness, scoring,
eval metrics, retrieval-quality services, hierarchical chunking, and privacy
config — all passing.

> **Action required:** run `alembic upgrade head` to apply migrations 005–007.

---

## What is genuinely still left

### Phase 9
- [ ] Memory-explorer page (browse stored sources / chunks / freshness / trust).
- [ ] A "smart routing" mode in the search box itself calling `/search/hybrid`
      (the CLI `--hybrid` already exposes this; the web search box does not).
- [ ] Optional Python SDK / client package.

### Phase 10
- [ ] Full deep-research pipeline — run every expansion variant as its own
      crawl, then dedup → rerank → citation-verify → synthesize a merged answer.
      DEEP mode currently widens the single crawl and rewrites the query; the
      multi-crawl/merge orchestration is the remaining piece.

### Phase 11
- [ ] In-UI metrics dashboard (latency, cache hit rate, vector vs web rate).
      The data exists via `agent_traces`; this is a frontend view.

### Phase 12
- [ ] Multi-tenant **workspaces** — per-workspace vector memory, trusted
      sources, and feedback history. This is the one deliberately deferred
      item: it requires adding a `workspace_id` to `queries`, `results`,
      `chunks`, `feedback`, and `source_trust` and threading a workspace filter
      through every retrieval query. That is a cross-cutting data-model change
      that must be developed against a live Postgres and integration-tested —
      shipping it blind would risk silently corrupting retrieval scoping.
- [ ] Admin dashboard UI (the `/admin/*` API exists; this is a frontend view).

Everything remaining is either a frontend view that needs a build loop, an SDK
package, or the multi-tenant refactor above — none can be completed to a
verifiable standard without a live stack (Postgres + Redis + Ollama) and
`npm run dev`.

---

## Verification notes

All new backend modules compile; 70+ pure-logic unit tests pass. Migrations
005–007 are additive (new columns with defaults / `IF NOT EXISTS`), consistent
with migrations 001–004, but have not been run against a live database in this
environment — apply and smoke-test them before relying on the new endpoints.
The React changes (feedback buttons, Insights tab) are additive and type-safe
but were not built with `npm run dev` here; build once before deploying.
