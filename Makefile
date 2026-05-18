.PHONY: help setup migrate test run dev clean docker-up docker-down docker-logs lint fmt

# Default target
help:
	@echo ""
	@echo "  Hybrid Search for Agents — available commands"
	@echo ""
	@echo "  Quick start:"
	@echo "    make setup        Install deps, copy .env, and start Docker services"
	@echo "    make migrate      Run Alembic database migrations"
	@echo "    make run          Start the API server (production mode, 4 workers)"
	@echo "    make dev          Start the API server (dev mode, auto-reload)"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-up    Start PostgreSQL + Redis in the background"
	@echo "    make docker-down  Stop all Docker services"
	@echo "    make docker-logs  Tail logs from all containers"
	@echo ""
	@echo "  Development:"
	@echo "    make test         Run all unit tests"
	@echo "    make lint         Run ruff linter"
	@echo "    make fmt          Auto-format with ruff"
	@echo "    make clean        Remove .pyc files and __pycache__ dirs"
	@echo ""
	@echo "  First time? Run:  make setup && make migrate && make dev"
	@echo ""

# ─── First-time setup ────────────────────────────────────────────────────────

setup:
	@echo "→ Checking for .env file..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "  ✓ Created .env from .env.example — edit it if you need custom values"; \
	else \
		echo "  ✓ .env already exists, skipping"; \
	fi
	@echo "→ Installing Python dependencies..."
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -r requirements.txt; \
	else \
		pip install -r requirements.txt; \
	fi
	@echo "→ Starting Docker services (PostgreSQL + Redis)..."
	@$(MAKE) docker-up
	@echo ""
	@echo "  ✓ Setup complete!"
	@echo "  Next steps:"
	@echo "    make migrate   — create the database schema"
	@echo "    make dev       — start the API server"
	@echo ""

# ─── Database ────────────────────────────────────────────────────────────────

migrate:
	@echo "→ Running database migrations..."
	@alembic upgrade head
	@echo "  ✓ Migrations applied"

migrate-status:
	@alembic current

migrate-rollback:
	@alembic downgrade -1

# ─── Run the server ──────────────────────────────────────────────────────────

run:
	@echo "→ Starting API server (production mode, 4 workers)..."
	@uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

dev:
	@echo "→ Starting API server (dev mode, auto-reload)..."
	@uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info

# ─── Docker ──────────────────────────────────────────────────────────────────

docker-up:
	@echo "→ Starting PostgreSQL and Redis..."
	@docker compose -f docker/docker-compose.yml up -d db cache
	@echo "  Waiting for services to be healthy..."
	@sleep 3
	@docker compose -f docker/docker-compose.yml ps

docker-down:
	@docker compose -f docker/docker-compose.yml down

docker-up-full:
	@echo "→ Starting full stack (API + DB + Redis)..."
	@docker compose -f docker/docker-compose.yml up -d
	@docker compose -f docker/docker-compose.yml ps

docker-logs:
	@docker compose -f docker/docker-compose.yml logs -f

docker-logs-api:
	@docker compose -f docker/docker-compose.yml logs -f api

# ─── Testing ─────────────────────────────────────────────────────────────────

test:
	@echo "→ Running tests..."
	@pytest tests/ -v

test-fast:
	@pytest tests/ -v -x --ignore=tests/test_search_endpoint.py

test-coverage:
	@pytest tests/ --cov=app --cov-report=term-missing

# ─── Code quality ────────────────────────────────────────────────────────────

lint:
	@ruff check app/ tests/

fmt:
	@ruff format app/ tests/

# ─── Cleanup ─────────────────────────────────────────────────────────────────

clean:
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "  ✓ Cleaned"

# ─── Quick smoke test (requires running server) ───────────────────────────────

smoke:
	@echo "→ Smoke-testing the running server..."
	@curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
	@echo ""
	@curl -s -X POST http://localhost:8000/api/v1/search \
		-H "Content-Type: application/json" \
		-d '{"query": "what is pgvector", "max_results": 2}' \
		| python3 -m json.tool | head -40
