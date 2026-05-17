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
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(384)")
    # Create IVFFlat index for fast approximate nearest-neighbor search
    # lists=100 is a good default for tables up to ~1M rows
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding")
