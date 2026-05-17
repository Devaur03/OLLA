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
