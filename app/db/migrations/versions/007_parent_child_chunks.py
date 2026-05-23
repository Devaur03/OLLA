"""Parent-child chunking (Phase 10)

Adds two columns to `chunks` so the store can hold a two-level hierarchy:

  - is_parent  — TRUE for a large "parent" chunk used to give the LLM wider
                 context at generation time.
  - parent_id  — on a small "child" chunk, points at the parent it belongs to.
                 Child chunks are what get embedded and retrieved; the parent
                 is expanded in for answer synthesis.

Both columns are nullable / default-safe, and parent-child chunking is opt-in
(`ENABLE_PARENT_CHILD_CHUNKING`), so existing rows and behaviour are unaffected.

Revision ID: 007
Revises: 006
Create Date: 2026-05-22
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
        "is_parent BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
        "parent_id VARCHAR(36)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_is_parent ON chunks(is_parent)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_is_parent")
    op.execute("DROP INDEX IF EXISTS idx_chunks_parent")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS parent_id")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS is_parent")
