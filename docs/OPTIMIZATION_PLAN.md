# DDGS Engine & Pipeline Optimization Plan

> Derived from `COMPARISON_README.md` (DDGS vs Turiya). This plan turns the
> comparison's roadmap into a concrete set of changes against the *actual*
> codebase, and records the decisions made while implementing them.

Status legend: ✅ done · 🔨 in progress · 📋 planned

---

## 0. Findings — the codebase as it actually is

A walk through the repo surfaced one structural problem the comparison README
did not mention: **the project ships two parallel, incompatible implementations
of the same pipeline.**

| Layer | Files | Used at runtime? |
|---|---|---|
| **Active pipeline** | `app/services/*` + `app/api/routes/search.py` | ✅ Yes — mounted in `app/main.py` |
| **Layered/DI pipeline** | `app/domain/*`, `app/infrastructure/*`, `app/container.py`, `app/api/v1/*` | ❌ No — never wired into `main.py`; `app/api/v1/routes` is empty |

Both contain a `DuckDuckGoSearch`, a Jina fetcher, a ranker, and a cache. Only
the `app/services/*` set serves traffic. The layered set is referenced **only by
unit tests**. This duplication is the root cause of the "which file do I edit?"
confusion and it doubles the maintenance surface.

The comparison README's code samples all target `app/services/search_service.py`
and `app/services/fetch_service.py` — i.e. the active path.

---

## 1. Architecture decision — unify on `app/services/*`

**Decision:** the `app/services/*` pipeline is the single source of truth.

Reasons: it is the code that actually serves requests; it is what the route
handlers, the MCP server, and the kept tests exercise; and it is what the
comparison README's roadmap is written against.

Actions:
- Move the dead layered code (`app/domain`, `app/infrastructure`, `container.py`,
  empty `app/api/v1`) into `archive/legacy_layered_architecture/` for reference.
- Rewrite `tests/conftest.py` so it no longer imports the archived layer.
- Remove the orphaned unit tests that only tested the archived layer.
- Salvage the genuinely useful idea from the layered version — explicit
  pipeline *stages with error isolation* — and rebuild it properly inside
  `app/services/` as a `SearchPipeline` orchestrator.

The result: **one** pipeline, **one** place to edit, no behavioural change for
API clients.

---

## 2. Pipeline restructure

Today `app/api/routes/search.py` is a 187-line "god handler" that wires every
stage together inline. If `clean()` throws, the failure is hard to trace and
nothing downstream runs (the exact fragility the README calls out in §2 and §7).

**New shape:**

```
app/api/routes/search.py   ── thin: parse request, call pipeline, return
        │
        ▼
app/services/pipeline.py   ── SearchPipeline orchestrator
        │   each stage wrapped in a trace span (success / failed / fallback)
        ├─ search   → SearchService      (multi-backend DDG + Brave)
        ├─ fetch    → FetchService       (Jina → direct → snippet waterfall)
        ├─ clean    → CleanService + SanitizeService
        ├─ chunk    → ChunkService
        ├─ rank     → RankService + CredibilityService
        ├─ store    → StoreService       (+ confidence, memory tier, entities)
        └─ graph    → GraphService       (build chunk_edges, async/non-fatal)
```

Each stage records an `agent_traces` row (Turiya-inspired, README §8/§10.5) so
the dashboard and logs can see exactly where a query slowed down or failed. A
stage failing is isolated: the pipeline degrades gracefully instead of 500-ing.

---

## 3. Feature roadmap (from COMPARISON_README §11)

### 🔴 Critical
| # | Feature | Plan |
|---|---|---|
| 1 | Multi-backend DDG search | `search_service.py`: loop `auto → html → lite`, catch per backend |
| 2 | Safe-search / timelimit / region | new enums in `models/request.py`, threaded through to DDG |
| 3 | Jina fallback chain | `fetch_service.py`: Jina → direct scrape → DDG snippet |

### 🟠 High priority
| # | Feature | Plan |
|---|---|---|
| 4 | Confidence per chunk | `chunks.confidence/retrieval_count/last_validated` cols + `ConfidenceService` |
| 5 | STM → LTM promotion + pruning | `chunks.memory_tier` col + `MemoryService` promote/prune |
| 6 | Agent trace logging | `agent_traces` table + trace spans in `SearchPipeline` |
| 7 | Time-filtered search | covered by feature 2 (`timelimit`) |

### 🟡 Milestone
| # | Feature | Plan |
|---|---|---|
| 8 | Knowledge graph edges | `chunk_edges` table + `GraphService.build_edges` (pgvector cosine) |
| 9 | Graph-traversal retrieval | `POST /api/v1/search/graph` endpoint, N-hop traversal |
| 10 | Proxy rotation | `ProxyService` scaffold, opt-in via `PROXY_POOL` env |
| 11 | Prompt-injection sanitization | `SanitizeService` in the clean stage |

### 🟢 Future
| # | Feature | Plan |
|---|---|---|
| 12 | Event-bus pipeline | the staged `SearchPipeline` is the lightweight version of this |
| 13 | Region-aware routing | covered by feature 2 (`region`) |
| 14 | Periodic consolidation | `MemoryService.consolidate` + schedulable entrypoint |
| 15 | spaCy entity extraction | `EntityService` (lazy spaCy load) + `chunks.entities` JSONB |

---

## 4. Database changes — migration `004`

```sql
ALTER TABLE chunks ADD COLUMN confidence       FLOAT       DEFAULT 0.5;
ALTER TABLE chunks ADD COLUMN retrieval_count  INTEGER     DEFAULT 0;
ALTER TABLE chunks ADD COLUMN last_validated   TIMESTAMPTZ;
ALTER TABLE chunks ADD COLUMN memory_tier      VARCHAR(10) DEFAULT 'stm';
ALTER TABLE chunks ADD COLUMN entities         JSONB       DEFAULT '[]';

CREATE TABLE chunk_edges (...);     -- semantic similarity graph
CREATE TABLE agent_traces (...);    -- per-stage pipeline observability
```

UUID columns stay `VARCHAR(36)` to match the existing schema convention.

---

## 5. Risk & rollout notes

- All new DB columns have defaults → migration is safe on existing rows.
- New pipeline stages (graph build, entity extraction, trace logging) are
  **non-fatal**: a failure logs a warning and the search still returns.
- spaCy and its model are optional — `EntityService` degrades to a no-op if the
  package/model is absent, so deployments without it keep working.
- The archived layered code is moved, not deleted, so nothing is lost.
- New search params default to current behaviour (`safesearch=moderate`,
  `timelimit=None`, `region=wt-wt`) → existing API clients are unaffected.

---

## 6. Implementation checklist

- [ ] Plan document (this file)
- [ ] Unify architecture — archive dead layer, fix tests
- [ ] Multi-backend search service
- [ ] Waterfall fetch service
- [ ] Request/response models + config
- [ ] SearchPipeline orchestrator + thin route
- [ ] Migration 004 + ORM models
- [ ] Prompt-injection sanitization
- [ ] Confidence + memory-tier services
- [ ] Knowledge graph service + graph route + entity extraction
- [ ] Verification (syntax + import checks)
