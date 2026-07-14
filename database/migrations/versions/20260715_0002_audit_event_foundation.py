"""Create the append-only audit-event foundation.

Revision ID: 20260715_0002
Revises: 20260715_0001
Create Date: 2026-07-15

This revision is immutable after application to any shared environment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0002"
down_revision: str | Sequence[str] | None = "20260715_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_module", sa.String(length=63), nullable=False),
        sa.Column(
            "schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("safe_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "actor_type IN ('anonymous', 'rider', 'driver', 'staff', "
            "'administrator', 'system', 'service')",
            name="ck_audit_events_valid_actor_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'denied', 'failed', 'cancelled')",
            name="ck_audit_events_valid_outcome",
        ),
        sa.CheckConstraint(
            "schema_version > 0", name="ck_audit_events_positive_schema_version"
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_audit_events"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_events_occurred_at",
        "audit_events",
        ["occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_events_actor",
        "audit_events",
        ["actor_type", "actor_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_events_resource",
        "audit_events",
        ["resource_type", "resource_id"],
        schema=SCHEMA,
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"], schema=SCHEMA)
    op.create_index(
        "ix_audit_events_correlation_id",
        "audit_events",
        ["correlation_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_events_outcome", "audit_events", ["outcome"], schema=SCHEMA
    )
    op.create_index(
        "uq_audit_events_idempotency",
        "audit_events",
        ["source_module", "action", "idempotency_key"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.execute("REVOKE ALL ON TABLE ayo.audit_events FROM PUBLIC")
    op.execute(
        """
        DO $ayo$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
                GRANT USAGE ON SCHEMA ayo TO ayo_runtime;
                GRANT SELECT, INSERT ON TABLE ayo.audit_events TO ayo_runtime;
                REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
                    ON TABLE ayo.audit_events FROM ayo_runtime;
            END IF;
        END
        $ayo$
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive audit-history downgrade is prohibited. Apply a reviewed "
        "forward fix or restore a verified backup."
    )
