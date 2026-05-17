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
    # We do the min_sim filtering in Python to bypass psycopg3 parameter binding edge-cases with custom operators.
    sql = text("""
        SELECT
            c.text AS chunk_text,
            c.char_count,
            r.title,
            r.url,
            r.score AS relevance_score,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM chunks c
        JOIN results r ON c.result_id = r.id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)

    try:
        params = {
            "embedding": vector_str,
            "top_k": request.top_k,
        }
        
        result = await db.execute(sql, params)
        rows = result.fetchall()
        
        print(f"DEBUG: Returned rows: {len(rows)}")
    except Exception as e:
        logger.error(f"Semantic search query failed: {e}")
        raise HTTPException(status_code=503, detail=f"Vector search failed: {str(e)}")

    chunks = []
    for row in rows:
        sim = round(float(row.similarity), 4)
        if sim >= request.min_similarity:
            chunks.append({
                "text": row.chunk_text,
                "char_count": row.char_count,
                "title": row.title,
                "url": row.url,
                "relevance_score": row.relevance_score,
                "similarity": sim,
            })

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
