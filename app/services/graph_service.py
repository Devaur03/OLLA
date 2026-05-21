"""
PURPOSE: Knowledge graph over chunks (COMPARISON_README §8, §10.6, §10.7).

Turiya's biggest structural advantage is a concept graph. This service builds
the DDGS equivalent: weighted `chunk_edges` between semantically similar chunks,
plus multi-hop graph-traversal retrieval.

Edges are built from chunk embeddings (pgvector cosine similarity). Building
requires chunks to already have embeddings — run `/search/embed-and-store`
first, or call `build_edges()` after embeddings exist.

Multi-hop retrieval finds seed chunks by vector similarity, then walks the
graph N hops to surface connected context that pure vector search would miss.
"""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


def _vec(embedding: list[float]) -> str:
    """Format an embedding as a pgvector literal string."""
    return "[" + ",".join(map(str, embedding)) + "]"


class GraphService:
    """Builds and traverses the chunk knowledge graph."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------- build

    async def build_edges(self, limit_chunks: int = 200) -> int:
        """
        Build semantic-similarity edges for chunks that have embeddings.

        For each candidate chunk, find its top-K most similar peers and draw an
        edge when cosine similarity ≥ the configured threshold. Edges are stored
        with chunk_a_id < chunk_b_id so the unique index dedupes undirected pairs.

        Returns the number of edges created. Non-fatal on error.
        """
        if not settings.enable_knowledge_graph:
            return 0
        try:
            rows = (
                await self.db.execute(
                    text(
                        """
                        SELECT id, embedding
                        FROM chunks
                        WHERE embedding IS NOT NULL
                        ORDER BY COALESCE(last_validated, NOW()) DESC
                        LIMIT :lim
                        """
                    ),
                    {"lim": limit_chunks},
                )
            ).fetchall()

            created = 0
            threshold = settings.graph_similarity_threshold
            for row in rows:
                similar = (
                    await self.db.execute(
                        text(
                            """
                            SELECT id,
                                   1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                            FROM chunks
                            WHERE id <> :cid AND embedding IS NOT NULL
                            ORDER BY embedding <=> CAST(:emb AS vector)
                            LIMIT :k
                            """
                        ),
                        {
                            "emb": str(row.embedding),
                            "cid": row.id,
                            "k": settings.graph_max_edges_per_chunk,
                        },
                    )
                ).fetchall()

                for peer in similar:
                    sim = float(peer.similarity)
                    if sim < threshold:
                        continue
                    a, b = sorted((row.id, peer.id))
                    result = await self.db.execute(
                        text(
                            """
                            INSERT INTO chunk_edges
                                (id, chunk_a_id, chunk_b_id, edge_type, weight)
                            VALUES (:id, :a, :b, 'semantic_similarity', :w)
                            ON CONFLICT (chunk_a_id, chunk_b_id) DO NOTHING
                            """
                        ),
                        {"id": str(uuid.uuid4()), "a": a, "b": b, "w": round(sim, 4)},
                    )
                    created += result.rowcount or 0

            await self.db.commit()
            if created:
                logger.info("GraphService: created %d chunk edge(s)", created)
            return created
        except Exception as e:  # noqa: BLE001 — graph building is non-fatal
            logger.warning("GraphService: build_edges failed: %s", e)
            await self.db.rollback()
            return 0

    # ---------------------------------------------------------- traverse

    async def graph_search(
        self, query_embedding: list[float], hops: int = 2,
        seed_k: int = 5, top_k: int = 20, min_similarity: float = 0.6,
    ) -> dict:
        """
        Multi-hop retrieval. Find seed chunks by vector similarity to the query,
        then traverse `chunk_edges` up to `hops` times to collect connected
        context. Returns seed chunks + the expanded neighbourhood.
        """
        emb = _vec(query_embedding)

        seeds = (
            await self.db.execute(
                text(
                    """
                    SELECT c.id, c.text, r.url AS url, r.title AS title,
                           1 - (c.embedding <=> CAST(:emb AS vector)) AS similarity
                    FROM chunks c
                    JOIN results r ON c.result_id = r.id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> CAST(:emb AS vector)
                    LIMIT :k
                    """
                ),
                {"emb": emb, "k": seed_k},
            )
        ).fetchall()

        seed_ids = [r.id for r in seeds if float(r.similarity) >= min_similarity]
        seed_chunks = [
            {
                "id": r.id, "text": r.text, "url": r.url, "title": r.title,
                "similarity": round(float(r.similarity), 4), "hop": 0,
            }
            for r in seeds
            if float(r.similarity) >= min_similarity
        ]

        visited: set[str] = set(seed_ids)
        frontier: list[str] = list(seed_ids)
        expanded: list[dict] = []

        for hop in range(1, hops + 1):
            if not frontier:
                break
            neighbours = (
                await self.db.execute(
                    text(
                        """
                        SELECT e.chunk_a_id, e.chunk_b_id, e.weight,
                               c.text, r.url, r.title
                        FROM chunk_edges e
                        JOIN chunks c ON c.id IN (e.chunk_a_id, e.chunk_b_id)
                        JOIN results r ON c.result_id = r.id
                        WHERE (e.chunk_a_id = ANY(:ids) OR e.chunk_b_id = ANY(:ids))
                        """
                    ),
                    {"ids": frontier},
                )
            ).fetchall()

            next_frontier: list[str] = []
            for n in neighbours:
                for cid in (n.chunk_a_id, n.chunk_b_id):
                    if cid in visited:
                        continue
                    visited.add(cid)
                    next_frontier.append(cid)
            # Record the connected chunk rows (deduped by `visited`).
            for n in neighbours:
                cand = n.chunk_b_id if n.chunk_a_id in frontier else n.chunk_a_id
                if cand in {c["id"] for c in expanded}:
                    continue
                expanded.append({
                    "id": cand, "text": n.text, "url": n.url, "title": n.title,
                    "edge_weight": round(float(n.weight), 4), "hop": hop,
                })
            frontier = next_frontier

        return {
            "seed_chunks": seed_chunks,
            "connected_chunks": expanded,
            "total_chunks": len(seed_chunks) + len(expanded),
            "hops": hops,
        }
