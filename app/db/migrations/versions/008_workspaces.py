"""Multi-tenant workspaces (Phase 12)

Creates the `workspaces` table and adds `workspace_id` foreign-key columns
to every retrieval / feedback / trust table so each workspace maintains its
own isolated data scope.

A well-known "Default" workspace (UUID 00000000-...) is seeded and used for
all legacy data and unauthenticated / static-key requests.

SourceTrust PK changes from (domain) to (workspace_id, domain).

Revision ID: 008
Revises: 007
Create Date: 2026-05-23
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

DEFAULT_WS = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # --- 1. Create workspaces table ----------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            id          VARCHAR(36) PRIMARY KEY,
            name        VARCHAR(255) NOT NULL,
            owner_id    VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )

    # --- 2. Seed a default workspace for legacy / static-key data ----------
    #    The owner is the first user, or a synthetic "system" user if none exists.
    op.execute(
        f"""
        INSERT INTO users (id, email, plan, is_active, created_at, updated_at)
        VALUES ('{DEFAULT_WS}', 'system@localhost', 'enterprise', TRUE, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO workspaces (id, name, owner_id)
        VALUES ('{DEFAULT_WS}', 'Default', '{DEFAULT_WS}')
        ON CONFLICT (id) DO NOTHING
        """
    )

    # --- 3. Add workspace_id to core tables --------------------------------
    for table in ("queries", "results", "chunks", "feedback", "api_keys"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            f"workspace_id VARCHAR(36) DEFAULT '{DEFAULT_WS}' "
            f"REFERENCES workspaces(id) ON DELETE CASCADE"
        )
        op.execute(
            f"UPDATE {table} SET workspace_id = '{DEFAULT_WS}' WHERE workspace_id IS NULL"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN workspace_id SET NOT NULL"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_workspace ON {table}(workspace_id)"
        )

    # --- 4. SourceTrust: add workspace_id + rebuild PK ---------------------
    op.execute(
        f"ALTER TABLE source_trust ADD COLUMN IF NOT EXISTS "
        f"workspace_id VARCHAR(36) DEFAULT '{DEFAULT_WS}' "
        f"REFERENCES workspaces(id) ON DELETE CASCADE"
    )
    op.execute(
        f"UPDATE source_trust SET workspace_id = '{DEFAULT_WS}' WHERE workspace_id IS NULL"
    )
    op.execute("ALTER TABLE source_trust ALTER COLUMN workspace_id SET NOT NULL")

    # Drop old single-column PK, add composite PK
    op.execute("ALTER TABLE source_trust DROP CONSTRAINT IF EXISTS source_trust_pkey")
    op.execute(
        "ALTER TABLE source_trust ADD PRIMARY KEY (workspace_id, domain)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_trust_workspace "
        "ON source_trust(workspace_id)"
    )


def downgrade() -> None:
    # Reverse the source_trust PK change
    op.execute("ALTER TABLE source_trust DROP CONSTRAINT IF EXISTS source_trust_pkey")
    op.execute("ALTER TABLE source_trust ADD PRIMARY KEY (domain)")
    op.execute("ALTER TABLE source_trust DROP COLUMN IF EXISTS workspace_id")
    op.execute("DROP INDEX IF EXISTS idx_source_trust_workspace")

    # Drop workspace_id from core tables
    for table in ("api_keys", "feedback", "chunks", "results", "queries"):
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_workspace")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS workspace_id")

    # Drop workspaces table + system user
    op.execute("DROP TABLE IF EXISTS workspaces")
    op.execute(f"DELETE FROM users WHERE id = '{DEFAULT_WS}'")
