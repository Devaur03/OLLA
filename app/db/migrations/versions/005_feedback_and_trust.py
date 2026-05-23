"""Feedback loop and feedback-aware ranking

Adds the Phase 5-7 layer:
  - results: last_refreshed_at, refresh_needed   (freshness routing)
  - chunks:  positive_feedback_count, negative_feedback_count, usefulness_score
  - feedback table:     answer/citation/chunk/source level feedback events
  - source_trust table: learned per-domain trust, separate from static
                        credibility weights

All new columns have defaults, so the migration is safe on existing rows.

Revision ID: 005
Revises: 004
Create Date: 2026-05-22
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- results: freshness routing columns (Phase 5) ---------------------
    op.execute(
        "ALTER TABLE results ADD COLUMN IF NOT EXISTS "
        "last_refreshed_at TIMESTAMPTZ DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE results ADD COLUMN IF NOT EXISTS "
        "refresh_needed BOOLEAN DEFAULT FALSE"
    )

    # --- chunks: feedback-aware ranking columns (Phase 7) -----------------
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
        "positive_feedback_count INTEGER DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
        "negative_feedback_count INTEGER DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS "
        "usefulness_score FLOAT DEFAULT 0.5"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_usefulness "
        "ON chunks(usefulness_score)"
    )

    # --- feedback: answer/citation/chunk/source events (Phase 6) ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id            VARCHAR(36) PRIMARY KEY,
            query_id      VARCHAR(36) REFERENCES queries(id) ON DELETE SET NULL,
            result_id     VARCHAR(36) REFERENCES results(id) ON DELETE SET NULL,
            chunk_id      VARCHAR(36) REFERENCES chunks(id)  ON DELETE SET NULL,
            source_domain VARCHAR(255),
            source_url    TEXT,
            level         VARCHAR(20)  NOT NULL,
            feedback_type VARCHAR(30)  NOT NULL,
            comment       TEXT,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_query  ON feedback(query_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_chunk  ON feedback(chunk_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_domain ON feedback(source_domain)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_type   ON feedback(feedback_type)")

    # --- source_trust: learned per-domain trust (Phase 7) -----------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_trust (
            domain                 VARCHAR(255) PRIMARY KEY,
            trust_score            FLOAT   DEFAULT 0.5,
            positive_count         INTEGER DEFAULT 0,
            negative_count         INTEGER DEFAULT 0,
            bad_source_count       INTEGER DEFAULT 0,
            outdated_count         INTEGER DEFAULT 0,
            citation_success_count INTEGER DEFAULT 0,
            refresh_needed         BOOLEAN DEFAULT FALSE,
            updated_at             TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_trust")
    op.execute("DROP TABLE IF EXISTS feedback")
    op.execute("DROP INDEX IF EXISTS idx_chunks_usefulness")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS usefulness_score")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS negative_feedback_count")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS positive_feedback_count")
    op.execute("ALTER TABLE results DROP COLUMN IF EXISTS refresh_needed")
    op.execute("ALTER TABLE results DROP COLUMN IF EXISTS last_refreshed_at")
