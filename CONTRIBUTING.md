# Contributing

Thanks for considering a contribution. Here's how to get set up and what's expected.

---

## Development setup

```bash
git clone https://github.com/YOUR_USERNAME/hybrid-search-agents.git
cd hybrid-search-agents
make setup      # installs deps, copies .env, starts Docker
make migrate    # creates the DB schema
make dev        # starts the server with auto-reload at :8000
```

Run tests at any point:
```bash
make test        # full suite
make test-fast   # skips integration tests that need a running server
```

---

## Project structure

```
app/
  api/
    routes/       # FastAPI route handlers (search, semantic, health)
    middleware/   # Auth middleware
  models/
    db/           # SQLAlchemy ORM models
    request.py    # Pydantic input models
    response.py   # Pydantic output models
  services/       # Business logic (one file per concern)
  config.py       # All settings via pydantic-settings
  main.py         # App factory
mcp_server/
  server.py       # MCP stdio server exposing web_search + semantic_search
tests/            # Pytest unit tests (no external deps required)
docker/           # Dockerfile + docker-compose.yml
```

The golden rule: **one service, one responsibility.** If you're adding a feature, add a new `*_service.py` file rather than growing an existing one.

---

## Branching

| Branch | Purpose |
|---|---|
| `main` | Stable, deployable |
| `Phase-N-*` | Feature branches for each development phase |
| Your branch | Fork from `main`, name it `feat/short-description` or `fix/short-description` |

---

## Making a change

1. Fork the repo and create a branch from `main`
2. Write or update tests for anything you change
3. Make sure `make test` and `make lint` both pass
4. Open a PR against `main` with a clear description of what changed and why

---

## PR checklist

- [ ] Tests pass locally (`make test`)
- [ ] Linter passes (`make lint`)
- [ ] New config values are added to both `config.py` **and** `.env.example`
- [ ] Actionable error messages for any new failure path
- [ ] No hardcoded secrets or localhost URLs in committed code

---

## Adding a new service

1. Create `app/services/your_service.py` with a single class
2. Add any new config keys to `app/config.py` and `.env.example`
3. Wire it into the relevant route in `app/api/routes/`
4. Add at least one test in `tests/test_your_service.py`

---

## Adding a new search provider

The system supports DDG (default) and Brave Search (fallback). To add another:

1. Add a `_search_<provider>()` method to `SearchService` in `app/services/search_service.py`
2. Add the provider's API key as an env var in `config.py` + `.env.example`
3. Hook it into the fallback chain in `search()`

---

## Questions

Open a GitHub Discussion or file an issue. We prefer issues over emails because the answers are searchable for future contributors.
