# ADR 0002 — Layered (onion) architecture

## Status
Accepted

## Context
The original codebase had all logic in flat `app/services/` modules: search,
fetch, embed, rank, cache, and persist were tightly coupled with no interfaces.
This made it hard to test, swap providers, or reason about dependencies.

## Decision
Adopt a four-layer architecture:

```
app/
├── domain/       # Pure Python — no I/O, no frameworks
│   ├── interfaces/   # ABCs for every external dependency
│   ├── models/       # Value objects (dataclasses)
│   └── services/     # SearchOrchestrator, ContentProcessor, RankingEngine
├── infrastructure/   # Implements domain interfaces (Redis, Postgres, Jina, BGE…)
├── core/             # Cross-cutting: config, logging, errors, tracing, utils
└── api/              # FastAPI thin controllers — calls domain, returns HTTP
```

**Dependency rule:** inner layers never import from outer layers.
`domain` has zero third-party imports. `infrastructure` depends on `domain` only.

## Consequences

**Positive:**
- Domain services are 100 % unit-testable without network or database.
- New providers (e.g. Tavily search, Cohere embeddings) need only implement an interface.
- Structured logging and tracing attach at the `core` layer without touching business logic.

**Negative:**
- More files and boilerplate than a flat structure.
- Developers must understand the layer rules before contributing.
- Dependency injection wiring (app/container.py) adds indirection.

## Revisit criteria
Revisit if the project shrinks to a single-developer script where the boilerplate
cost outweighs the testability benefit.
