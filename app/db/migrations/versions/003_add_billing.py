"""Add users, api_keys, and usage_events for billing + metering

Revision ID: 003
Revises: 002
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

revision      = "003"
down_revision = "002"
branch_labels = None
depends_on    = None

PLANS = ("free", "starter", "pro", "team", "enterprise")


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",                     sa.String(36),  primary_key=True),
        sa.Column("email",                  sa.String(255), nullable=False, unique=True),
        sa.Column("stripe_customer_id",     sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("plan",                   sa.String(50),  nullable=False, server_default="free"),
        sa.Column("is_active",              sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )
    op.create_index("idx_users_email",              "users", ["email"],              unique=True)
    op.create_index("idx_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=False)

    # ── api_keys ───────────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("user_id",     sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash",    sa.String(64),  nullable=False, unique=True),
        sa.Column("key_prefix",  sa.String(20),  nullable=False),   # e.g. "hsa_1234abcd"
        sa.Column("name",        sa.String(255), nullable=False, server_default="Default key"),
        sa.Column("is_active",   sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_api_keys_user_id",   "api_keys", ["user_id"])
    op.create_index("idx_api_keys_key_hash",  "api_keys", ["key_hash"], unique=True)

    # ── usage_events ───────────────────────────────────────────────────────────
    op.create_table(
        "usage_events",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("api_key_id",      sa.String(36),
                  sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id",         sa.String(36),
                  sa.ForeignKey("users.id",    ondelete="SET NULL"), nullable=True),
        sa.Column("endpoint",        sa.String(100), nullable=False),
        sa.Column("response_time_ms", sa.Integer(),  nullable=True),
        sa.Column("cache_hit",        sa.Boolean(),  nullable=False, server_default="false"),
        sa.Column("status_code",      sa.Integer(),  nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_usage_events_user_id",    "usage_events", ["user_id"])
    op.create_index("idx_usage_events_api_key_id", "usage_events", ["api_key_id"])
    # Composite index for fast monthly-count queries: WHERE user_id=? AND created_at > ?
    op.create_index(
        "idx_usage_events_user_month",
        "usage_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("usage_events")
    op.drop_table("api_keys")
    op.drop_table("users")
