# Hybrid Search for Agents — Part 2: Scale & Production
## Execution Guide for Claude (Phases 2–5)

---

## IMPORTANT: READ THIS FIRST

This document picks up where `README_PART1_MVP.md` left off. The MVP from Part 1 must be fully working before you start here. All verification checklist items in Part 1 must be confirmed.

This guide is fully self-contained. Every file, migration, config, and command is specified. Follow it in order. Do not change module names, class names, or file paths — they are referenced across files.

**What this document builds (in order):**
- Phase 2A: PostgreSQL storage with SQLAlchemy (async ORM)
- Phase 2B: Redis caching layer (repeat queries in <50ms)
- Phase 3: Vector embeddings + pgvector semantic search
- Phase 4: MCP server for agent/Claude tool integration
- Phase 5: Auth, rate limiting, credibility scoring, citation generation, Docker Compose

---

## Updated Final Folder Structure

```
hybrid-search-agents/
├── app/
│   ├── __init__.py
│   ├── main.py                       ← MODIFIED in Phase 2A
│   ├── config.py                     ← MODIFIED in Phase 2A
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py           ← MODIFIED in Phase 5
│   │   ├── middleware/               ← NEW in Phase 5
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   └── rate_limit.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       ├── search.py             ← MODIFIED in Phase 2B
│   │       └── semantic.py           ← NEW in Phase 3
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py                ← MODIFIED in Phase 3
│   │   ├── response.py
│   │   └── db/                       ← NEW in Phase 2A
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── query.py
│   │       ├── result.py
│   │       └── chunk.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── search_service.py
│   │   ├── fetch_service.py
│   │   ├── clean_service.py
│   │   ├── chunk_service.py
│   │   ├── rank_service.py
│   │   ├── cache_service.py          ← NEW in Phase 2B
│   │   ├── store_service.py          ← NEW in Phase 2A
│   │   ├── embed_service.py          ← NEW in Phase 3
│   │   ├── credibility_service.py    ← NEW in Phase 5
│   │   └── citation_service.py       ← NEW in Phase 5
│   └── db/
│       ├── __init__.py
│       ├── session.py                ← NEW in Phase 2A
│       └── migrations/               ← NEW in Phase 2A
│           ├── env.py
│           ├── script.py.mako
│           └── versions/
│               ├── 001_initial.py
│               └── 002_add_vectors.py
├── mcp/                              ← NEW in Phase 4
│   ├── __init__.py
│   └── server.py
├── docker/                           ← NEW in Phase 5
│   ├── Dockerfile
│   └── docker-compose.yml
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   ← MODIFIED in Phase 2A
│   ├── test_clean_service.py
│   ├── test_chunk_service.py
│   ├── test_rank_service.py
│   ├── test_search_endpoint.py
│   ├── test_cache_service.py         ← NEW in Phase 2B
│   ├── test_store_service.py         ← NEW in Phase 2A
│   └── test_semantic_endpoint.py     ← NEW in Phase 3
├── .env.example                      ← MODIFIED throughout
├── .env                              ← MODIFIED throughout
└── pyproject.toml                    ← MODIFIED in Phase 2A
```

---

## Phase 2A: PostgreSQL Storage

### Goal
Persist every query and its results to PostgreSQL so that:
1. Query history is available for analytics
2. Results can be queried later without re-fetching
3. The database is ready for vector columns in Phase 3

### Step 2A-1: Install New Dependencies

```bash
# RUN THIS COMMAND
pip install sqlalchemy[asyncio] asyncpg alembic

# Update pyproject.toml dependencies section — ADD these lines to the dependencies list:
# "sqlalchemy[asyncio]>=2.0.0",
# "asyncpg>=0.29.0",
# "alembic>=1.13.0",
```

### Step 2A-2: Start PostgreSQL

If you don't have PostgreSQL locally, use Docker:

```bash
# RUN THIS COMMAND
docker run -d \
  --name hybrid-search-db \
  -e POSTGRES_DB=hybriddb \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

The `pgvector/pgvector:pg16` image includes both PostgreSQL 16 and the pgvector extension. Use this image — not plain `postgres` — so you won't need to reinstall pgvector in Phase 3.

### Step 2A-3: Update `.env`

```bash
# MODIFY THIS FILE AT: .env
# ADD these lines to the existing content

DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/hybriddb"
DATABASE_ECHO=false
```

```bash
# MODIFY THIS FILE AT: .env.example
# ADD these lines

DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/hybriddb"
DATABASE_ECHO=false
```

### Step 2A-4: Update `app/config.py`

```python
# REPLACE THE ENTIRE CONTENTS OF: app/config.py

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "Hybrid Search for Agents"
    app_version: str = "0.1.0"
    debug: bool = False

    # Search
    max_search_results: int = 5
    max_chars_per_page: int = 8000
    fetch_timeout_seconds: int = 15
    max_concurrent_fetches: int = 5

    # Chunking
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50

    # Fetch API
    fetch_base_url: str = "https://r.jina.ai"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/hybriddb"
    database_echo: bool = False

    # Redis (Phase 2B)
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600  # 1 hour

    # Embeddings (Phase 3)
    openai_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    use_local_embeddings: bool = False  # True = use BGE instead of OpenAI

    # Auth (Phase 5)
    api_keys: str = ""  # Comma-separated list of valid API keys
    require_auth: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_api_keys(self) -> set[str]:
        """Parse comma-separated API keys into a set."""
        if not self.api_keys:
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

### Step 2A-5: Create DB Session

```python
# CREATE THIS FILE AT: app/db/__init__.py
# (empty file)
```

```python
# CREATE THIS FILE AT: app/db/session.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before use
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncSession:
    """
    FastAPI dependency that yields a database session.
    Session is committed and closed after the request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Step 2A-6: Create DB Models

```python
# CREATE THIS FILE AT: app/models/db/__init__.py
# (empty file)
```

```python
# CREATE THIS FILE AT: app/models/db/base.py

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass
```

```python
# CREATE THIS FILE AT: app/models/db/query.py

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.db.base import Base


class StoredQuery(Base):
    """Persisted search query with metadata."""
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Relationship: one query → many results
    results: Mapped[list["StoredResult"]] = relationship(
        "StoredResult", back_populates="query", cascade="all, delete-orphan"
    )
```

```python
# CREATE THIS FILE AT: app/models/db/result.py

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.db.base import Base


class StoredResult(Base):
    """Persisted search result linked to a query."""
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    query: Mapped["StoredQuery"] = relationship("StoredQuery", back_populates="results")
    chunks: Mapped[list["StoredChunk"]] = relationship(
        "StoredChunk", back_populates="result", cascade="all, delete-orphan"
    )
```

```python
# CREATE THIS FILE AT: app/models/db/chunk.py

import uuid
from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.db.base import Base


class StoredChunk(Base):
    """
    Persisted text chunk.
    The `embedding` column is added in Phase 3 via Alembic migration
    once the pgvector extension is enabled.
    """
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("results.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # embedding column added in Phase 3 migration

    result: Mapped["StoredResult"] = relationship("StoredResult", back_populates="chunks")
```

### Step 2A-7: Create Alembic Migrations

```bash
# RUN THESE COMMANDS from project root
alembic init app/db/migrations
```

Now replace the generated `app/db/migrations/env.py`:

```python
# REPLACE THE ENTIRE CONTENTS OF: app/db/migrations/env.py

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import all models so Alembic can detect them
from app.models.db.base import Base
from app.models.db.query import StoredQuery     # noqa: F401
from app.models.db.result import StoredResult   # noqa: F401
from app.models.db.chunk import StoredChunk     # noqa: F401
from app.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create the initial migration:

```python
# CREATE THIS FILE AT: app/db/migrations/versions/001_initial.py

"""Initial schema: queries, results, chunks

Revision ID: 001
Revises:
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("result_count", sa.Integer, default=0),
        sa.Column("processing_ms", sa.Integer, default=0),
    )
    op.create_index("idx_queries_hash", "queries", ["query_hash"])

    op.create_table(
        "results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query_id", sa.String(36), sa.ForeignKey("queries.id", ondelete="CASCADE")),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("score", sa.Float, default=0.0),
        sa.Column("char_count", sa.Integer, default=0),
        sa.Column("chunk_count", sa.Integer, default=0),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_results_query_id", "results", ["query_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("result_id", sa.String(36), sa.ForeignKey("results.id", ondelete="CASCADE")),
        sa.Column("chunk_id", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("char_count", sa.Integer, default=0),
    )
    op.create_index("idx_chunks_result_id", "chunks", ["result_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("results")
    op.drop_table("queries")
```

```bash
# RUN THIS COMMAND to apply migrations
alembic upgrade head
```

### Step 2A-8: Create StoreService

```python
# CREATE THIS FILE AT: app/services/store_service.py
#
# PURPOSE: Persist search queries and their results to PostgreSQL.
# Called at the end of the search pipeline after ranking.
# Non-blocking — storage failure should NOT fail the search response.

import hashlib
import json
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db.query import StoredQuery
from app.models.db.result import StoredResult
from app.models.db.chunk import StoredChunk
from app.models.response import SearchResult

logger = logging.getLogger(__name__)


def hash_query(query: str, params: dict) -> str:
    """
    Create a deterministic SHA-256 hash for a query + params combination.
    Used to detect duplicate queries and for cache key generation.
    """
    raw = f"{query.lower().strip()}:{json.dumps(params, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


class StoreService:
    """Persists search results to PostgreSQL."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save(
        self,
        query: str,
        params: dict,
        results: list[SearchResult],
        processing_ms: int,
    ) -> str:
        """
        Save a query and all its results to the database.

        Args:
            query: The search query string.
            params: Dict of search parameters (for hash generation).
            results: Ranked list of SearchResult objects.
            processing_ms: Total pipeline duration.

        Returns:
            The UUID of the saved query record.
        """
        try:
            query_hash = hash_query(query, params)
            query_id = str(uuid.uuid4())

            # Save the query record
            stored_query = StoredQuery(
                id=query_id,
                query_text=query,
                query_hash=query_hash,
                result_count=len(results),
                processing_ms=processing_ms,
            )
            self.db.add(stored_query)

            # Save each result and its chunks
            for result in results:
                result_id = str(uuid.uuid4())
                stored_result = StoredResult(
                    id=result_id,
                    query_id=query_id,
                    rank=result.rank,
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    score=result.score,
                    char_count=result.char_count,
                    chunk_count=result.chunk_count,
                )
                self.db.add(stored_result)

                for chunk in result.chunks:
                    stored_chunk = StoredChunk(
                        id=str(uuid.uuid4()),
                        result_id=result_id,
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        char_count=chunk.char_count,
                    )
                    self.db.add(stored_chunk)

            await self.db.flush()
            logger.info(f"StoreService: saved query '{query}' with {len(results)} results")
            return query_id

        except Exception as e:
            logger.error(f"StoreService: failed to save results: {e}")
            raise
```

---

## Phase 2B: Redis Caching

### Goal
Cache search responses in Redis with a 1-hour TTL. Repeat queries with identical parameters return instantly without hitting DuckDuckGo or Jina.

### Step 2B-1: Start Redis

```bash
# RUN THIS COMMAND
docker run -d \
  --name hybrid-search-cache \
  -p 6379:6379 \
  redis:7-alpine
```

### Step 2B-2: Install Redis Client

```bash
pip install "redis[asyncio]>=5.0.0"
```

### Step 2B-3: Create CacheService

```python
# CREATE THIS FILE AT: app/services/cache_service.py
#
# PURPOSE: Redis-backed cache for search responses.
# Cache key = SHA-256 hash of (query + search parameters).
# TTL defaults to 3600 seconds (1 hour), configurable in .env.
#
# Cache flow:
# 1. On every search: compute cache key
# 2. Check Redis for existing response
# 3. Cache hit → return immediately (skips all fetching)
# 4. Cache miss → run pipeline, then store response in Redis
#
# The entire SearchResponse is serialized to JSON and stored as a single Redis string.

import json
import hashlib
import logging
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Redis-backed cache for SearchResponse objects."""

    def __init__(self):
        self.client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        self.ttl = settings.cache_ttl_seconds

    def make_key(self, query: str, params: dict) -> str:
        """
        Generate a unique cache key for a query + params combination.
        Keys are SHA-256 hashes to keep them fixed-length and collision-resistant.
        """
        raw = f"{query.lower().strip()}:{json.dumps(params, sort_keys=True)}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"search:{digest}"

    async def get(self, key: str) -> dict | None:
        """
        Retrieve a cached response.

        Returns:
            Parsed dict if cache hit, None if cache miss or Redis error.
        """
        try:
            data = await self.client.get(key)
            if data:
                logger.debug(f"CacheService: HIT for key {key[:16]}...")
                return json.loads(data)
            logger.debug(f"CacheService: MISS for key {key[:16]}...")
            return None
        except Exception as e:
            logger.warning(f"CacheService: get failed: {e}")
            return None  # Cache failure should never break the search

    async def set(self, key: str, value: dict) -> bool:
        """
        Store a response in Redis with TTL.

        Returns:
            True on success, False on failure.
        """
        try:
            await self.client.setex(key, self.ttl, json.dumps(value))
            logger.debug(f"CacheService: SET key {key[:16]}... (TTL={self.ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"CacheService: set failed: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a specific cache key."""
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"CacheService: delete failed: {e}")
            return False

    async def flush_all(self) -> bool:
        """
        Flush all search cache keys.
        Uses SCAN to safely iterate — never calls FLUSHALL on the whole database.
        """
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self.client.scan(cursor, match="search:*", count=100)
                if keys:
                    await self.client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            logger.info(f"CacheService: flushed {deleted} keys")
            return True
        except Exception as e:
            logger.error(f"CacheService: flush_all failed: {e}")
            return False

    async def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
```

### Step 2B-4: Update `app/api/routes/search.py` to use Cache + Store

```python
# REPLACE THE ENTIRE CONTENTS OF: app/api/routes/search.py

import time
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request import SearchRequest
from app.models.response import SearchResponse, SearchResult, ProcessedResult
from app.services.search_service import SearchService
from app.services.fetch_service import FetchService
from app.services.clean_service import CleanService
from app.services.chunk_service import ChunkService
from app.services.rank_service import RankService
from app.services.cache_service import CacheService
from app.services.store_service import StoreService
from app.db.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Main search endpoint with Redis caching and PostgreSQL persistence.

    Pipeline:
    1. Check Redis cache (cache hit → return immediately)
    2. DuckDuckGo search → candidate URLs
    3. Concurrent Jina Reader fetch → raw markdown
    4. Clean → remove noise
    5. Chunk → RAG-ready segments
    6. Rank → sort by relevance score
    7. Store to PostgreSQL (non-blocking, failure safe)
    8. Store to Redis cache
    9. Return structured JSON
    """
    start_time = time.monotonic()

    search_params = {
        "max_results": request.max_results,
        "max_chars_per_page": request.max_chars_per_page,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
    }

    # --- CACHE CHECK ---
    cache_service = CacheService()
    cache_key = cache_service.make_key(request.query, search_params)
    cached = await cache_service.get(cache_key)

    if cached:
        logger.info(f"Cache HIT for '{request.query}' — returning cached response")
        cached["cache_hit"] = True
        return SearchResponse(**cached)

    logger.info(f"Cache MISS for '{request.query}' — running pipeline")

    try:
        # --- STEP 1: Search ---
        search_service = SearchService(max_results=request.max_results)
        candidates = await search_service.search(request.query)

        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No results found for query: '{request.query}'"
            )

        # --- STEP 2: Fetch ---
        fetch_service = FetchService()
        fetched_pages = await fetch_service.fetch_all(
            candidates=candidates,
            max_chars=request.max_chars_per_page,
        )

        if not fetched_pages:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch content from any search result URLs"
            )

        # --- STEP 3: Clean + Chunk ---
        clean_service = CleanService()
        chunk_service = ChunkService(
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        processed_results: list[ProcessedResult] = []
        for page in fetched_pages:
            cleaned_content = clean_service.clean(page.raw_content)
            if not cleaned_content:
                continue
            chunks = chunk_service.chunk(cleaned_content)
            processed_results.append(
                ProcessedResult(
                    title=page.title,
                    url=page.url,
                    content=cleaned_content,
                    chunks=chunks,
                    score=0.0,
                )
            )

        if not processed_results:
            raise HTTPException(status_code=503, detail="All pages had empty content after cleaning")

        # --- STEP 4: Rank ---
        rank_service = RankService()
        ranked_results = rank_service.rank(request.query, processed_results)

        # --- STEP 5: Build Final Results ---
        final_results: list[SearchResult] = []
        for rank_pos, result in enumerate(ranked_results, start=1):
            if result.score < request.min_score:
                continue
            final_results.append(
                SearchResult(
                    rank=rank_pos,
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    chunks=result.chunks,
                    score=result.score,
                    char_count=len(result.content),
                    chunk_count=len(result.chunks),
                )
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        response = SearchResponse(
            query=request.query,
            total_results=len(final_results),
            processing_time_ms=elapsed_ms,
            results=final_results,
        )

        # --- STEP 6: Store to DB (non-blocking, failure safe) ---
        try:
            store_service = StoreService(db)
            await store_service.save(
                query=request.query,
                params=search_params,
                results=final_results,
                processing_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"DB storage failed (non-fatal): {e}")

        # --- STEP 7: Store to Cache ---
        await cache_service.set(cache_key, response.model_dump())

        logger.info(
            f"Search complete: '{request.query}' → {len(final_results)} results "
            f"in {elapsed_ms}ms (cached)"
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Search pipeline failed: {str(e)}")
```

---

## Phase 3: Embeddings & Semantic Search

### Goal
Embed each stored chunk as a vector, store in pgvector, and expose a `/search/semantic` endpoint for pure vector similarity search.

### Step 3-1: Install Dependencies

```bash
pip install openai pgvector numpy
```

### Step 3-2: Add pgvector Migration

```python
# CREATE THIS FILE AT: app/db/migrations/versions/002_add_vectors.py

"""Add embedding column to chunks using pgvector

Revision ID: 002
Revises: 001
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (safe to call even if already enabled)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Add embedding column to chunks (1536 dims for OpenAI text-embedding-3-small)
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    # Create IVFFlat index for fast approximate nearest-neighbor search
    # lists=100 is a good default for tables up to ~1M rows
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding")
```

```bash
# RUN THIS COMMAND to apply the vector migration
alembic upgrade head
```

### Step 3-3: Create EmbedService

```python
# CREATE THIS FILE AT: app/services/embed_service.py
#
# PURPOSE: Generate vector embeddings for text chunks.
#
# Two modes:
#   1. OpenAI API (use_local_embeddings=False): Uses text-embedding-3-small
#      - 1536 dimensions
#      - Best quality, requires OPENAI_API_KEY in .env
#   2. Local BGE (use_local_embeddings=True): Uses BAAI/bge-small-en-v1.5
#      - 384 dimensions — NOTE: if using local, change migration to vector(384)
#      - Free, private, runs on CPU
#      - Install: pip install sentence-transformers
#
# Default: OpenAI. Set USE_LOCAL_EMBEDDINGS=true in .env to switch.

import logging
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)


class EmbedService:
    """
    Generates text embeddings for semantic search.
    Supports OpenAI API and local sentence-transformers (BGE).
    """

    def __init__(self):
        self.use_local = settings.use_local_embeddings
        self._local_model = None

        if not self.use_local and not settings.openai_api_key:
            logger.warning(
                "EmbedService: OPENAI_API_KEY not set and use_local_embeddings=False. "
                "Semantic search will not work. Set OPENAI_API_KEY or USE_LOCAL_EMBEDDINGS=true."
            )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).
            Returns empty list on failure.
        """
        if not texts:
            return []

        try:
            if self.use_local:
                return await self._embed_local(texts)
            else:
                return await self._embed_openai(texts)
        except Exception as e:
            logger.error(f"EmbedService: embedding failed: {e}")
            return []

    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a single query string.
        Returns empty list on failure.
        """
        results = await self.embed_texts([query])
        return results[0] if results else []

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed using OpenAI text-embedding-3-small API."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        # OpenAI supports batching — send all texts in one request
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Embed using local BGE model via sentence-transformers."""
        if self._local_model is None:
            # Lazy load to avoid import error if sentence-transformers not installed
            try:
                from sentence_transformers import SentenceTransformer
                self._local_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
                logger.info("EmbedService: loaded local BGE model")
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )

        # Run in executor to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._local_model.encode(
                texts, normalize_embeddings=True
            ).tolist()
        )
        return embeddings
```

### Step 3-4: Add Semantic Search Endpoint

First, add the new request model to `app/models/request.py`:

```python
# ADD THIS CLASS to the END of: app/models/request.py
# (Do not remove existing SearchRequest — add after it)

class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Semantic search query")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of chunks to return")
    min_similarity: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum cosine similarity threshold"
    )
```

Now create the semantic route:

```python
# CREATE THIS FILE AT: app/api/routes/semantic.py
#
# PURPOSE: Semantic search endpoint using pgvector.
# Embeds the query, finds similar stored chunks via cosine similarity,
# and returns matching results WITHOUT making new web requests.
#
# This endpoint searches only content that was previously fetched and stored
# via the /search endpoint. It's fast (<100ms) and works entirely from the DB.

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.request import SemanticSearchRequest
from app.services.embed_service import EmbedService
from app.db.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["semantic"])


@router.post("/search/semantic")
async def semantic_search(
    request: SemanticSearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Semantic search using pgvector cosine similarity.

    Embeds the query, then finds the most similar stored chunks.
    Requires content to have been previously stored via /search.
    """
    embed_service = EmbedService()

    # Embed the query
    query_embedding = await embed_service.embed_query(request.query)

    if not query_embedding:
        raise HTTPException(
            status_code=503,
            detail="Failed to generate query embedding. Check OPENAI_API_KEY or local model."
        )

    # Build embedding vector string for pgvector
    vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Cosine similarity search using pgvector operator (<=>)
    # 1 - distance = similarity (we want similarity, pgvector gives distance)
    sql = text("""
        SELECT
            c.text AS chunk_text,
            c.char_count,
            r.title,
            r.url,
            r.score AS relevance_score,
            1 - (c.embedding <=> :embedding ::vector) AS similarity
        FROM chunks c
        JOIN results r ON c.result_id = r.id
        WHERE c.embedding IS NOT NULL
          AND 1 - (c.embedding <=> :embedding ::vector) >= :min_sim
        ORDER BY c.embedding <=> :embedding ::vector
        LIMIT :top_k
    """)

    try:
        result = await db.execute(
            sql,
            {
                "embedding": vector_str,
                "min_sim": request.min_similarity,
                "top_k": request.top_k,
            }
        )
        rows = result.fetchall()
    except Exception as e:
        logger.error(f"Semantic search query failed: {e}")
        raise HTTPException(status_code=503, detail=f"Vector search failed: {str(e)}")

    chunks = [
        {
            "text": row.chunk_text,
            "char_count": row.char_count,
            "title": row.title,
            "url": row.url,
            "relevance_score": row.relevance_score,
            "similarity": round(float(row.similarity), 4),
        }
        for row in rows
    ]

    return {
        "query": request.query,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }


@router.post("/search/embed-and-store")
async def embed_stored_chunks(db: AsyncSession = Depends(get_db_session)):
    """
    Utility endpoint: generates embeddings for all stored chunks that
    don't have an embedding yet. Call this after bulk-importing data
    or to backfill embeddings after enabling Phase 3.

    Processes chunks in batches of 50 to avoid API rate limits.
    """
    embed_service = EmbedService()

    # Find chunks without embeddings
    result = await db.execute(
        text("SELECT id, text FROM chunks WHERE embedding IS NULL LIMIT 500")
    )
    rows = result.fetchall()

    if not rows:
        return {"message": "All chunks already have embeddings", "processed": 0}

    batch_size = 50
    processed = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [row.text for row in batch]
        embeddings = await embed_service.embed_texts(texts)

        if not embeddings:
            continue

        for row, embedding in zip(batch, embeddings):
            vector_str = "[" + ",".join(map(str, embedding)) + "]"
            await db.execute(
                text("UPDATE chunks SET embedding = :emb ::vector WHERE id = :id"),
                {"emb": vector_str, "id": row.id}
            )
            processed += 1

        await db.commit()
        logger.info(f"Embedded batch {i // batch_size + 1}: {processed} chunks done")

    return {"message": "Embedding complete", "processed": processed}
```

### Step 3-5: Register Semantic Route in `app/main.py`

```python
# MODIFY app/main.py
# ADD this import after the existing route imports:
from app.api.routes import semantic

# ADD this line inside create_app() after the existing include_router calls:
app.include_router(semantic.router, prefix="/api/v1")
```

---

## Phase 4: MCP Server for Agent Integration

### Goal
Expose the retrieval system as an MCP (Model Context Protocol) server. This allows Claude Desktop, Cursor, and any MCP-compatible client to use hybrid search as a native tool — no custom integration code needed.

### Step 4-1: Install MCP

```bash
pip install mcp
```

### Step 4-2: Create MCP Server

```python
# CREATE THIS FILE AT: mcp/__init__.py
# (empty file)
```

```python
# CREATE THIS FILE AT: mcp/server.py
#
# PURPOSE: MCP server that exposes hybrid search as a tool.
#
# How it works:
# - The MCP server exposes one tool: `web_search`
# - When called by an AI agent, it posts to the local FastAPI server
# - The FastAPI server runs the full pipeline and returns JSON
# - The MCP server returns the JSON string back to the agent
#
# To use with Claude Desktop:
# 1. Start the FastAPI server: uvicorn app.main:app --port 8000
# 2. Run this MCP server: python -m mcp.server
# 3. Add to claude_desktop_config.json (see below)
#
# claude_desktop_config.json entry:
# {
#   "mcpServers": {
#     "hybrid-search": {
#       "command": "python",
#       "args": ["-m", "mcp.server"],
#       "cwd": "/absolute/path/to/hybrid-search-agents"
#     }
#   }
# }

import asyncio
import json
import logging
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The FastAPI backend URL — must be running before starting this MCP server
BACKEND_URL = "http://localhost:8000/api/v1"

server = Server("hybrid-search-agents")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Declare the tools this MCP server provides."""
    return [
        types.Tool(
            name="web_search",
            description=(
                "Search the web and return clean, chunked, ranked content "
                "suitable for AI agent grounding and RAG pipelines. "
                "Returns structured JSON with title, URL, clean text, "
                "text chunks, and relevance scores for each result."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of web pages to retrieve (1-10)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "chunk_size": {
                        "type": "integer",
                        "description": "Target character size for each text chunk",
                        "default": 500,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="semantic_search",
            description=(
                "Search previously retrieved content using vector similarity. "
                "Finds semantically relevant chunks from the knowledge base "
                "without making new web requests. Fast (<100ms). "
                "Use this when you want to find related content from past searches."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The semantic search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of similar chunks to return",
                        "default": 10,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0.0–1.0)",
                        "default": 0.6,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str,
    arguments: dict,
) -> list[types.TextContent]:
    """Handle tool calls from AI agents."""

    if name == "web_search":
        return await _handle_web_search(arguments)
    elif name == "semantic_search":
        return await _handle_semantic_search(arguments)
    else:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]


async def _handle_web_search(arguments: dict) -> list[types.TextContent]:
    """Handle web_search tool call."""
    try:
        payload = {
            "query": arguments["query"],
            "max_results": arguments.get("max_results", 5),
            "chunk_size": arguments.get("chunk_size", 500),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/search",
                json=payload,
            )
            response.raise_for_status()

        return [types.TextContent(type="text", text=response.text)]

    except httpx.ConnectError:
        error = {
            "error": "Cannot connect to Hybrid Search backend",
            "detail": f"Is the FastAPI server running at {BACKEND_URL}?",
        }
        return [types.TextContent(type="text", text=json.dumps(error))]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def _handle_semantic_search(arguments: dict) -> list[types.TextContent]:
    """Handle semantic_search tool call."""
    try:
        payload = {
            "query": arguments["query"],
            "top_k": arguments.get("top_k", 10),
            "min_similarity": arguments.get("min_similarity", 0.6),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/search/semantic",
                json=payload,
            )
            response.raise_for_status()

        return [types.TextContent(type="text", text=response.text)]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def main():
    """Run the MCP server over stdio."""
    logger.info("Starting Hybrid Search MCP Server")
    logger.info(f"Backend URL: {BACKEND_URL}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Phase 5: Auth, Credibility, Citations & Docker

### Step 5-1: API Key Authentication Middleware

```python
# CREATE THIS FILE AT: app/api/middleware/__init__.py
# (empty file)
```

```python
# CREATE THIS FILE AT: app/api/middleware/auth.py
#
# PURPOSE: API key authentication for production deployments.
# Disabled by default (REQUIRE_AUTH=false in .env).
# Enable by setting REQUIRE_AUTH=true and API_KEYS=key1,key2 in .env.

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Paths that do not require authentication
PUBLIC_PATHS = {"/api/v1/health", "/docs", "/redoc", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    API key authentication middleware.
    Checks X-API-Key header against the configured set of valid keys.
    Only active when REQUIRE_AUTH=true.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth if not required
        if not settings.require_auth:
            return await call_next(request)

        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        valid_keys = settings.get_api_keys()

        if not api_key or api_key not in valid_keys:
            logger.warning(
                f"AuthMiddleware: rejected request from {request.client.host} "
                f"— invalid or missing API key"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing API key. Pass X-API-Key header."}
            )

        return await call_next(request)
```

### Step 5-2: CredibilityService

```python
# CREATE THIS FILE AT: app/services/credibility_service.py
#
# PURPOSE: Assign a credibility score to a URL based on its domain.
# Used as a signal in the final ranking formula:
#   final_score = (relevance * 0.7) + (credibility * 0.3)
#
# Credibility tiers:
#   HIGH (0.85-0.95): Academic, official docs, established references
#   MEDIUM (0.65-0.8): Quality blogs, well-known developer resources
#   LOW (0.4-0.55): Forums, user-generated content, aggregators
#   DEFAULT (0.5): Unknown domains

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DOMAIN_CREDIBILITY: dict[str, float] = {
    # Academic & research
    "arxiv.org": 0.95,
    "scholar.google.com": 0.95,
    "pubmed.ncbi.nlm.nih.gov": 0.95,
    "nature.com": 0.95,
    "ieee.org": 0.92,
    "acm.org": 0.92,

    # Official documentation
    "docs.python.org": 0.95,
    "docs.microsoft.com": 0.92,
    "developer.mozilla.org": 0.95,
    "kubernetes.io": 0.92,
    "docs.docker.com": 0.92,
    "fastapi.tiangolo.com": 0.90,
    "docs.sqlalchemy.org": 0.90,
    "docs.pydantic.dev": 0.90,
    "redis.io": 0.90,
    "postgresql.org": 0.90,

    # Established references
    "wikipedia.org": 0.80,
    "github.com": 0.85,
    "stackoverflow.com": 0.82,

    # Quality tech blogs
    "aws.amazon.com": 0.88,
    "cloud.google.com": 0.88,
    "azure.microsoft.com": 0.88,
    "openai.com": 0.88,
    "anthropic.com": 0.88,
    "huggingface.co": 0.85,
    "towardsdatascience.com": 0.70,
    "medium.com": 0.60,
    "dev.to": 0.65,
    "hashnode.com": 0.62,

    # Lower credibility
    "reddit.com": 0.50,
    "quora.com": 0.45,
}


class CredibilityService:
    """
    Assigns domain-based credibility scores to URLs.
    """

    def score(self, url: str) -> float:
        """
        Returns credibility score (0.0–1.0) for a URL.

        Args:
            url: Full URL string.

        Returns:
            Float between 0.0 and 1.0. Default 0.5 for unknown domains.
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Strip www. prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Exact match first
            if domain in DOMAIN_CREDIBILITY:
                return DOMAIN_CREDIBILITY[domain]

            # Partial match (e.g. sub.stackoverflow.com)
            for known_domain, score in DOMAIN_CREDIBILITY.items():
                if domain.endswith(f".{known_domain}"):
                    return score

            return 0.5  # Unknown domain default

        except Exception:
            return 0.5
```

### Step 5-3: CitationService

```python
# CREATE THIS FILE AT: app/services/citation_service.py
#
# PURPOSE: Generate formatted citations for search results.
# Useful for agents that need to provide source attribution.

from datetime import date
from app.models.response import SearchResult
import logging

logger = logging.getLogger(__name__)


class CitationService:
    """Generates formatted citations in multiple styles."""

    def generate_apa(self, result: SearchResult) -> str:
        """APA style citation."""
        today = date.today().strftime("%Y, %B %d")
        title = result.title or result.url
        return f"{title}. (n.d.). Retrieved {today}, from {result.url}"

    def generate_markdown_link(self, result: SearchResult) -> str:
        """Markdown hyperlink citation."""
        title = result.title or result.url
        return f"[{title}]({result.url})"

    def generate_citations_block(self, results: list[SearchResult]) -> str:
        """
        Generate a full citations section in markdown format.
        Suitable for appending to agent-generated content.
        """
        if not results:
            return ""

        lines = ["## Sources\n"]
        for i, result in enumerate(results, 1):
            title = result.title or result.url
            today = date.today().strftime("%Y-%m-%d")
            lines.append(
                f"{i}. [{title}]({result.url}) "
                f"— Relevance: {result.score:.2f} "
                f"— Retrieved: {today}"
            )

        return "\n".join(lines)

    def generate_json_citations(self, results: list[SearchResult]) -> list[dict]:
        """
        Generate machine-readable citation objects.
        Useful for agents that need to process citations programmatically.
        """
        today = date.today().isoformat()
        return [
            {
                "rank": result.rank,
                "title": result.title,
                "url": result.url,
                "score": result.score,
                "retrieved_date": today,
                "apa": self.generate_apa(result),
                "markdown": self.generate_markdown_link(result),
            }
            for result in results
        ]
```

### Step 5-4: Update `app/main.py` to Include All Middleware

```python
# REPLACE THE ENTIRE CONTENTS OF: app/main.py

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import health, search, semantic
from app.api.middleware.auth import AuthMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Web retrieval system for AI agents and RAG applications. "
            "Supports web search, content extraction, chunking, semantic search, "
            "and MCP agent integration."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth middleware (only active when REQUIRE_AUTH=true)
    app.add_middleware(AuthMiddleware)

    # Routes
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(semantic.router, prefix="/api/v1")

    @app.on_event("startup")
    async def on_startup():
        logger.info(f"Starting {settings.app_name} v{settings.app_version}")
        logger.info(f"Auth required: {settings.require_auth}")
        logger.info(f"Database: {settings.database_url.split('@')[-1]}")

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Shutting down application")

    return app


app = create_app()
```

### Step 5-5: Docker Compose

```dockerfile
# CREATE THIS FILE AT: docker/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY mcp/ ./mcp/
COPY .env .env

EXPOSE 8000

# Run with 4 workers for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```yaml
# CREATE THIS FILE AT: docker/docker-compose.yml

version: "3.9"

services:
  # FastAPI application
  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: "postgresql+asyncpg://postgres:password@db:5432/hybriddb"
      REDIS_URL: "redis://cache:6379"
      DATABASE_ECHO: "false"
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # PostgreSQL with pgvector
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: hybriddb
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d hybriddb"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis cache
  cache:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
  redisdata:
```

Create `requirements.txt` for Docker:

```bash
# RUN THIS COMMAND to generate requirements.txt
pip freeze > requirements.txt
```

### Step 5-6: Build and Run with Docker Compose

```bash
# RUN FROM PROJECT ROOT
cd docker
docker-compose up --build

# Or run in background
docker-compose up --build -d

# Run migrations inside the container
docker-compose exec api alembic upgrade head

# Check logs
docker-compose logs -f api
```

---

## Final Verification Checklist

Before considering Part 2 complete, verify each item:

### Phase 2A (PostgreSQL)
- [ ] `docker ps` shows `hybrid-search-db` container running
- [ ] `alembic upgrade head` completes without errors
- [ ] After running a search, rows appear in `queries`, `results`, `chunks` tables
- [ ] DB storage failure does NOT cause search endpoint to return an error

### Phase 2B (Redis)
- [ ] `docker ps` shows `hybrid-search-cache` container running
- [ ] First search call: `processing_time_ms` is ~1500–3000
- [ ] Second identical search call: `processing_time_ms` is <100 (cache hit)
- [ ] `CacheService.ping()` returns True in a test

### Phase 3 (Embeddings)
- [ ] `OPENAI_API_KEY` set in `.env` (or `USE_LOCAL_EMBEDDINGS=true`)
- [ ] `POST /api/v1/search/embed-and-store` runs without error after storing data
- [ ] `POST /api/v1/search/semantic` returns chunks for a relevant query
- [ ] Semantic search returns empty results for unrelated queries
- [ ] Migration `002_add_vectors.py` applied: `chunks.embedding` column exists

### Phase 4 (MCP)
- [ ] `python -m mcp.server` starts without errors
- [ ] FastAPI server is running on port 8000 before starting MCP server
- [ ] Claude Desktop config updated with correct `cwd` path
- [ ] Claude can call `web_search` tool from within Claude Desktop

### Phase 5 (Production)
- [ ] `REQUIRE_AUTH=true` + valid `API_KEYS` in `.env` → requests without key return 403
- [ ] `REQUIRE_AUTH=false` → all requests pass through without auth check
- [ ] `/api/v1/health` returns 200 even when auth is required
- [ ] `docker-compose up` starts all 3 services (api, db, cache)
- [ ] Docker healthchecks pass for all services

---

## Summary of All Environment Variables

```bash
# .env — full example with all phases

# Core
APP_NAME="Hybrid Search for Agents"
APP_VERSION="0.1.0"
DEBUG=false

# Search
MAX_SEARCH_RESULTS=5
MAX_CHARS_PER_PAGE=8000
FETCH_TIMEOUT_SECONDS=15
MAX_CONCURRENT_FETCHES=5
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50
FETCH_BASE_URL="https://r.jina.ai"

# Phase 2A: PostgreSQL
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/hybriddb"
DATABASE_ECHO=false

# Phase 2B: Redis
REDIS_URL="redis://localhost:6379"
CACHE_TTL_SECONDS=3600

# Phase 3: Embeddings
OPENAI_API_KEY="sk-..."
EMBEDDING_MODEL="text-embedding-3-small"
EMBEDDING_DIMENSIONS=1536
USE_LOCAL_EMBEDDINGS=false

# Phase 5: Auth
REQUIRE_AUTH=false
API_KEYS="key1,key2,key3"
```

---

*End of Part 2 — Scale & Production Build Instructions*
