"""
Knowledge-graph routes (COMPARISON_README §10.7).

  POST /api/v1/search/graph  — multi-hop graph-traversal retrieval
  POST /api/v1/graph/build   — (re)build chunk_edges from embeddings
  GET  /api/v1/graph/stats   — edge/tier counts for the dashboard
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.request import GraphSearchRequest
from app.services.embed_service import EmbedService
from app.services.graph_service import GraphService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph"])


@router.post("/search/graph")
async def graph_search(
    request: GraphSearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Multi-hop retrieval: seed by vector similarity, then walk chunk_edges to
    surface connected context that pure vector search would miss.
    """
    embed_service = EmbedService()
    query_embedding = await embed_service.embed_query(request.query)
    if not query_embedding:
        raise HTTPException(
            status_code=503,
            detail="Failed to generate query embedding. Check embedding configuration.",
        )

    graph = GraphService(db)
    result = await graph.graph_search(
        query_embedding=query_embedding,
        hops=request.hops,
        seed_k=request.seed_k,
        top_k=request.top_k,
        min_similarity=request.min_similarity,
    )
    # Trim connected chunks to top_k.
    result["connected_chunks"] = result["connected_chunks"][: request.top_k]
    result["query"] = request.query
    return result


@router.post("/graph/build")
async def graph_build(
    limit_chunks: int = 200,
    db: AsyncSession = Depends(get_db_session),
):
    """
    (Re)build semantic-similarity edges between embedded chunks.
    Run after embeddings have been generated via /search/embed-and-store.
    """
    graph = GraphService(db)
    created = await graph.build_edges(limit_chunks=limit_chunks)
    return {"message": "Graph build complete", "edges_created": created}


@router.get("/graph/stats")
async def graph_stats(db: AsyncSession = Depends(get_db_session)):
    """Return edge counts and memory-tier stats for the dashboard."""
    edge_row = (
        await db.execute(text("SELECT COUNT(*) AS n FROM chunk_edges"))
    ).fetchone()
    memory = MemoryService(db)
    tiers = await memory.stats()
    return {
        "total_edges": int(edge_row.n) if edge_row else 0,
        "memory_tiers": tiers,
    }
