"""
PostgreSQL implementation of SearchRepository using async SQLAlchemy.

Schema (from existing migrations):
  - search_queries  (id SERIAL, query_text TEXT, created_at TIMESTAMPTZ)
  - search_results  (id SERIAL, query_id INT, title TEXT, url TEXT,
                     score FLOAT, rank INT, char_count INT, chunk_count INT, content TEXT)
  - content_chunks  (id SERIAL, result_id INT, chunk_text TEXT, embedding VECTOR)
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.repository import SearchRepository, StoredSearchResult
from app.core.errors.exceptions import PersistenceError

logger = logging.getLogger(__name__)


class PostgresSearchRepository(SearchRepository):
    """
    Async PostgreSQL repository backed by an injected AsyncSession.

    Session lifecycle (commit / rollback / close) is managed by the FastAPI
    dependency in app/db/session.py; this class never commits or closes directly.

    Args:
        session: An active AsyncSession provided by the DI layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # SearchRepository interface
    # ------------------------------------------------------------------

    async def save(self, payload: StoredSearchResult) -> str:
        """
        Persist the search query, results, and embedded chunks.

        Args:
            payload: StoredSearchResult with query text, results list, and metadata.

        Returns:
            String representation of the saved query_id.

        Raises:
            PersistenceError: On any database error.
        """
        try:
            query_id = await self._insert_query(payload.query)
            for result in payload.results:
                result_id = await self._insert_result(query_id, result)
                for chunk in result.get("chunks", []):
                    await self._insert_chunk(result_id, chunk)
            logger.info(
                "PostgresSearchRepository: saved query_id=%s (%s results)",
                query_id, len(payload.results),
            )
            return str(query_id)
        except Exception as exc:
            raise PersistenceError("Failed to save search results: " + str(exc)) from exc

    async def health_check(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _insert_query(self, query_text: str) -> int:
        result = await self._session.execute(
            text(
                "INSERT INTO search_queries (query_text, created_at) "
                "VALUES (:q, NOW()) RETURNING id"
            ),
            {"q": query_text},
        )
        return result.fetchone()[0]

    async def _insert_result(self, query_id: int, result: dict) -> int:
        row = await self._session.execute(
            text(
                "INSERT INTO search_results "
                "  (query_id, title, url, score, rank, char_count, chunk_count, content) "
                "VALUES (:qid, :title, :url, :score, :rank, :cc, :chunks, :content) "
                "RETURNING id"
            ),
            {
                "qid": query_id,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "score": result.get("score", 0.0),
                "rank": result.get("rank", 0),
                "cc": result.get("char_count", 0),
                "chunks": result.get("chunk_count", 0),
                "content": (result.get("content") or "")[:50000],
            },
        )
        return row.fetchone()[0]

    async def _insert_chunk(self, result_id: int, chunk: dict) -> None:
        embedding = chunk.get("embedding")
        if embedding:
            emb_str = "[" + ",".join(str(x) for x in embedding) + "]"
            await self._session.execute(
                text(
                    "INSERT INTO content_chunks (result_id, chunk_text, embedding) "
                    "VALUES (:rid, :text, :emb::vector)"
                ),
                {"rid": result_id, "text": chunk.get("text", ""), "emb": emb_str},
            )
        else:
            await self._session.execute(
                text(
                    "INSERT INTO content_chunks (result_id, chunk_text) "
                    "VALUES (:rid, :text)"
                ),
                {"rid": result_id, "text": chunk.get("text", "")},
            )
