"""API key roles (Phase 12 RBAC)

Adds a `role` column to api_keys so endpoints can be gated by role:
  - admin   — full access, including the /api/v1/admin/* operator endpoints
  - member  — normal API access (the default for every existing key)

The column defaults to 'member', so the migration is safe on existing rows
and no key loses access to the non-admin API.

Revision ID: 006
Revises: 005
Create Date: 2026-05-22
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS "
        "role VARCHAR(20) DEFAULT 'member'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_role ON api_keys(role)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_keys_role")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS role")
