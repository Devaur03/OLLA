import hashlib
import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db.query import StoredQuery
from app.models.db.result import StoredResult
from app.models.db.chunk import StoredChunk
from app.models.response import SearchResult
from app.services.chunk_service import ChunkService

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

                # Phase 10: when parent-child chunking is enabled, store a
                # two-level hierarchy derived from the result content instead
                # of the flat chunk list.
                if settings.enable_parent_child_chunking and result.content:
                    self._add_hierarchical_chunks(result_id, result.content)
                else:
                    for chunk in result.chunks:
                        stored_chunk = StoredChunk(
                            id=str(uuid.uuid4()),
                            result_id=result_id,
                            chunk_id=chunk.chunk_id,
                            text=chunk.text,
                            char_count=chunk.char_count,
                            # New chunks start in short-term memory at default
                            # confidence; entities are populated when spaCy is on.
                            memory_tier="stm",
                            entities=getattr(chunk, "entities", []) or [],
                        )
                        self.db.add(stored_chunk)

            await self.db.flush()
            logger.info(f"StoreService: saved query '{query}' with {len(results)} results")
            return query_id

        except Exception as e:
            logger.error(f"StoreService: failed to save results: {e}")
            raise

    def _add_hierarchical_chunks(self, result_id: str, content: str) -> None:
        """
        Store parent + child chunks for one result (Phase 10).

        Parents (is_parent=True) carry wide context; children (is_parent=False)
        carry a `parent_id` back to their parent and are what gets embedded.
        """
        hier = ChunkService(
            chunk_size=settings.default_chunk_size,
            overlap=settings.default_chunk_overlap,
        ).chunk_hierarchical(content, parent_size=settings.parent_chunk_size)

        parent_ids: list[str] = []
        for parent in hier["parents"]:
            pid = str(uuid.uuid4())
            parent_ids.append(pid)
            self.db.add(StoredChunk(
                id=pid, result_id=result_id, chunk_id=parent.chunk_id,
                text=parent.text, char_count=parent.char_count,
                memory_tier="stm", is_parent=True,
            ))
        for child in hier["children"]:
            ch = child["chunk"]
            self.db.add(StoredChunk(
                id=str(uuid.uuid4()), result_id=result_id, chunk_id=ch.chunk_id,
                text=ch.text, char_count=ch.char_count, memory_tier="stm",
                is_parent=False, parent_id=parent_ids[child["parent_index"]],
            ))
