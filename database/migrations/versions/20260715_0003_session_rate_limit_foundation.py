"""Create durable session and rate-limit persistence.

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15

This revision is immutable after application to any shared environment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0003"
down_revision: str | Sequence[str] | None = "20260715_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revocation_reason IS NULL)",
            name="ck_sessions_consistent_revocation",
        ),
        sa.CheckConstraint("version > 0", name="ck_sessions_positive_version"),
        sa.CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason ~ "
            "'^[a-z][a-z0-9_.-]{0,63}$'",
            name="ck_sessions_safe_revocation_reason",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_sessions_valid_lifetime"
        ),
        sa.PrimaryKeyConstraint("session_id", name="pk_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_sessions_subject_id", "sessions", ["subject_id"], schema=SCHEMA)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], schema=SCHEMA)
    op.create_index(
        "ix_sessions_active_subject",
        "sessions",
        ["subject_id", "expires_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("policy_name", sa.String(length=63), nullable=False),
        sa.Column("tokens", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("last_refill_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tokens >= 0", name="ck_rate_limit_buckets_nonnegative_tokens"
        ),
        sa.PrimaryKeyConstraint(
            "key_hash", "policy_name", name="pk_rate_limit_buckets"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_rate_limit_buckets_updated_at",
        "rate_limit_buckets",
        ["updated_at"],
        schema=SCHEMA,
    )
    op.execute("REVOKE ALL ON TABLE ayo.sessions FROM PUBLIC")
    op.execute("REVOKE ALL ON TABLE ayo.rate_limit_buckets FROM PUBLIC")
    op.execute(
        """
        DO $ayo$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
                GRANT USAGE ON SCHEMA ayo TO ayo_runtime;
                GRANT SELECT, INSERT, UPDATE ON TABLE ayo.sessions TO ayo_runtime;
                GRANT SELECT, INSERT, UPDATE
                    ON TABLE ayo.rate_limit_buckets TO ayo_runtime;
                REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
                    ON TABLE ayo.sessions, ayo.rate_limit_buckets FROM ayo_runtime;
            END IF;
        END
        $ayo$
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive session/rate-limit downgrade is prohibited. Apply a reviewed "
        "forward fix or restore a verified backup."
    )
