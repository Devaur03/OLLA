"""Confidence scoring, memory tiers, knowledge graph, and agent traces

Adds the Turiya-inspired self-improving layer (COMPARISON_README §6, §8, §10):
  - chunks: confidence, retrieval_count, last_validated, memory_tier, entities
  - chunk_edges: semantic-similarity knowledge graph
  - agent_traces: per-stage pipeline observability

All new chunk columns have defaults, so the migration is safe on existing rows.

Revision ID: 004
Revises: 003
Create Date: 2026-05-20
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- chunks: confidence + memory tier columns -------------------------
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 0.5")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS retrieval_count INTEGER DEFAULT 0")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS last_validated TIMESTAMPTZ")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS memory_tier VARCHAR(10) DEFAULT 'stm'")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '[]'::jsonb")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_memory_tier ON chunks(memory_tier)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_confidence ON chunks(confidence)")

    # --- chunk_edges: knowledge graph -------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_edges (
            id          VARCHAR(36) PRIMARY KEY,
            chunk_a_id  VARCHAR(36) NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            chunk_b_id  VARCHAR(36) NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            edge_type   VARCHAR(50) DEFAULT 'semantic_similarity',
            weight      FLOAT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunk_edges_a ON chunk_edges(chunk_a_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunk_edges_b ON chunk_edges(chunk_b_id)")
    # Prevent duplicate edges between the same ordered pair.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_edges_pair "
        "ON chunk_edges(chunk_a_id, chunk_b_id)"
    )

    # --- agent_traces: pipeline observability -----------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_traces (
            id          VARCHAR(36) PRIMARY KEY,
            query_id    VARCHAR(36) REFERENCES queries(id) ON DELETE SET NULL,
            stage       VARCHAR(50) NOT NULL,
            status      VARCHAR(20) NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            metadata    JSONB,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_traces_query ON agent_traces(query_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_traces_stage ON agent_traces(stage)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_traces")
    op.execute("DROP TABLE IF EXISTS chunk_edges")
    op.execute("DROP INDEX IF EXISTS idx_chunks_confidence")
    op.execute("DROP INDEX IF EXISTS idx_chunks_memory_tier")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS entities")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS memory_tier")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS last_validated")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS retrieval_count")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS confidence")
