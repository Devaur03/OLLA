"""
PURPOSE: Inspect and refresh individual stored sources (Phase 8).

Two operations agents and operators repeatedly need:

  get_source(result_id)     — read one stored result and its chunks back out,
                              including its freshness / trust signals.
  refresh_source(result_id) — re-crawl that URL, replace its cleaned content
                              and chunks, stamp `last_refreshed_at`, and clear
                              the `refresh_needed` flag.

`refresh_source` reuses the normal fetch → clean → chunk services, so a
refreshed source is processed identically to a freshly crawled one. Embeddings
for the new chunks are left NULL — run `/search/embed-and-store` to backfill.
"""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.response import SearchCandidate
from app.services.chunk_service import ChunkService
from app.services.clean_service import CleanService
from app.services.fetch_service import FetchService

logger = logging.getLogger(__name__)


class SourcesService:
    """Reads and refreshes individual stored results."""

    def __init__(self, db: AsyncSession, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id

    async def get_source(self, result_id: str) -> dict | None:
        """Return one stored result plus its chunks, or None if not found."""
        row = (
            await self.db.execute(
                text(
                    """
                    SELECT id, query_id, rank, title, url, content, score,
                           char_count, chunk_count, fetched_at,
                           last_refreshed_at, refresh_needed
                    FROM results WHERE id = :rid AND workspace_id = :ws
                    """
                ),
                {"rid": result_id, "ws": self.workspace_id},
            )
        ).first()
        if not row:
            return None

        chunks = (
            await self.db.execute(
                text(
                    """
                    SELECT id, chunk_id, text, char_count, confidence,
                           usefulness_score, memory_tier
                    FROM chunks WHERE result_id = :rid AND workspace_id = :ws ORDER BY chunk_id
                    """
                ),
                {"rid": result_id, "ws": self.workspace_id},
            )
        ).fetchall()

        src = {k: _json(v) for k, v in row._mapping.items()}
        src["chunks"] = [{k: _json(v) for k, v in c._mapping.items()} for c in chunks]
        return src

    async def refresh_source(self, result_id: str) -> dict:
        """
        Re-crawl a stored result's URL and replace its content + chunks.

        Returns a summary dict. Raises LookupError if the result_id is unknown
        and RuntimeError if the page could not be re-fetched.
        """
        row = (
            await self.db.execute(
                text("SELECT id, url, title FROM results WHERE id = :rid AND workspace_id = :ws"),
                {"rid": result_id, "ws": self.workspace_id},
            )
        ).first()
        if not row:
            raise LookupError(f"result {result_id} not found")

        # --- re-fetch -----------------------------------------------------
        pages = await FetchService().fetch_all(
            candidates=[SearchCandidate(title=row.title or "", url=row.url)],
            max_chars=settings.max_chars_per_page,
        )
        if not pages:
            raise RuntimeError(f"could not re-fetch {row.url}")

        cleaned = CleanService().clean(pages[0].raw_content)
        if not cleaned:
            raise RuntimeError(f"{row.url} had empty content after cleaning")

        chunks = ChunkService(
            chunk_size=settings.default_chunk_size,
            overlap=settings.default_chunk_overlap,
        ).chunk(cleaned)

        # --- replace stored content + chunks ------------------------------
        await self.db.execute(
            text("DELETE FROM chunks WHERE result_id = :rid AND workspace_id = :ws"), 
            {"rid": result_id, "ws": self.workspace_id}
        )
        for ch in chunks:
            await self.db.execute(
                text(
                    """
                    INSERT INTO chunks (id, result_id, chunk_id, text, char_count,
                                        memory_tier, workspace_id)
                    VALUES (:id, :rid, :cidx, :txt, :cc, 'stm', :ws)
                    """
                ),
                {
                    "id": str(uuid.uuid4()), "rid": result_id,
                    "cidx": ch.chunk_id, "txt": ch.text, "cc": ch.char_count,
                    "ws": self.workspace_id,
                },
            )
        await self.db.execute(
            text(
                """
                UPDATE results SET
                    content = :content,
                    char_count = :cc,
                    chunk_count = :n,
                    last_refreshed_at = NOW(),
                    refresh_needed = FALSE
                WHERE id = :rid AND workspace_id = :ws
                """
            ),
            {"content": cleaned, "cc": len(cleaned), "n": len(chunks), "rid": result_id, "ws": self.workspace_id},
        )
        logger.info("SourcesService: refreshed %s (%d chunks)", row.url, len(chunks))
        return {
            "result_id": result_id,
            "url": row.url,
            "refreshed": True,
            "char_count": len(cleaned),
            "chunk_count": len(chunks),
            "fetch_method": pages[0].fetch_method,
            "note": "embeddings cleared — run /search/embed-and-store to backfill",
        }


def _json(value):
    """Make a DB cell JSON-serialisable."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
