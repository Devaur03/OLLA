# ADR 0001 — Use pgvector instead of a dedicated vector database

## Status
Accepted

## Context
Hybrid Search needs vector storage for semantic search over embedded content chunks.
Evaluated options:

| Option | Hosting | Extra infra | ANN algorithm | Cost |
|--------|---------|-------------|---------------|------|
| **pgvector** (PostgreSQL extension) | Self-hosted | None | IVFFlat + HNSW | Free |
| Pinecone | Managed | Yes | HNSW | $70+/mo |
| Qdrant | Self/managed | Yes | HNSW | Free / $25+/mo |
| Weaviate | Self/managed | Yes | HNSW | Free / custom |

## Decision
Use **pgvector** as the vector storage layer, collocated with the main PostgreSQL
database that already stores search queries, results, and chunks.

## Consequences

**Positive:**
- Single database simplifies operations, backups, and transactions.
- Self-hosted — full data ownership, no vendor lock-in.
- No additional infrastructure: the existing `pgvector/pgvector:pg16` Docker image
  provides both relational and vector capabilities.
- Mature PostgreSQL ecosystem (connection pooling, HA, read replicas).
- IVFFlat index covers our expected volume (<1 M vectors) with sub-10 ms queries.
- HNSW index (pgvector >= 0.5) available when higher recall is needed.

**Negative:**
- Slightly lower recall than dedicated vector DBs at very high cardinality (>50 M vectors).
- Vector operations compete for PostgreSQL resources under heavy write load.
- No built-in metadata filtering as ergonomic as Pinecone/Qdrant namespaces.

## Revisit criteria
Reconsider if:
- The embeddings corpus exceeds **10 million vectors**, OR
- Semantic search latency exceeds **50 ms p99** after index tuning, OR
- The team needs multi-tenant namespace isolation that pgvector cannot provide.
