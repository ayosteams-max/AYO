"""Add reusable persistence idempotency, event and outbox kernel.

Revision ID: 20260723_0044
Revises: 20260721_0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0044"
down_revision: str | Sequence[str] | None = "20260721_0043"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "persistence_idempotency_records",
        sa.Column("scope", sa.String(127), nullable=False),
        sa.Column("actor_reference", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_reference", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "scope ~ '^[a-z][a-z0-9_.-]{1,126}$'",
            name="ck_persistence_idempotency_records_valid_scope",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[a-f0-9]{64}$'",
            name="ck_persistence_idempotency_records_valid_request_hash",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR (completed_at >= created_at "
            "AND response_reference IS NOT NULL)",
            name="ck_persistence_idempotency_records_valid_completion",
        ),
        sa.PrimaryKeyConstraint(
            "scope",
            "actor_reference",
            "idempotency_key",
            name="pk_persistence_idempotency_records",
        ),
        sa.UniqueConstraint(
            "command_id", name="uq_persistence_idempotency_records_command_id"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "persistence_domain_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(127), nullable=False),
        sa.Column("aggregate_type", sa.String(127), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("source_module", sa.String(127), nullable=False),
        sa.Column(
            "schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(128)),
        sa.CheckConstraint(
            "schema_version > 0",
            name="ck_persistence_domain_events_positive_schema_version",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_persistence_domain_events"),
        sa.UniqueConstraint(
            "source_module",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "idempotency_key",
            name="uq_persistence_domain_events_event_idempotency",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_persistence_domain_events_aggregate",
        "persistence_domain_events",
        ["aggregate_type", "aggregate_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_persistence_domain_events_correlation",
        "persistence_domain_events",
        ["correlation_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "persistence_outbox",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.persistence_domain_events.event_id"),
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(64)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(63)),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_persistence_outbox_nonnegative_attempts",
        ),
        sa.CheckConstraint(
            "(claimed_at IS NULL) = (claimed_by IS NULL)",
            name="ck_persistence_outbox_complete_claim",
        ),
        sa.CheckConstraint(
            "NOT (published_at IS NOT NULL AND dead_lettered_at IS NOT NULL)",
            name="ck_persistence_outbox_single_terminal_state",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_persistence_outbox"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_persistence_outbox_pending",
        "persistence_outbox",
        ["available_at", "event_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NULL AND dead_lettered_at IS NULL"),
    )
    op.execute("REVOKE ALL ON ayo.persistence_domain_events FROM PUBLIC")
    op.execute("REVOKE ALL ON ayo.persistence_outbox FROM PUBLIC")
    op.execute("REVOKE ALL ON ayo.persistence_idempotency_records FROM PUBLIC")
    op.execute(
        """
        DO $ayo$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
                GRANT SELECT, INSERT ON ayo.persistence_domain_events TO ayo_runtime;
                REVOKE UPDATE, DELETE, TRUNCATE ON ayo.persistence_domain_events
                    FROM ayo_runtime;
                GRANT SELECT, INSERT, UPDATE ON ayo.persistence_outbox TO ayo_runtime;
                REVOKE DELETE, TRUNCATE ON ayo.persistence_outbox FROM ayo_runtime;
                GRANT SELECT, INSERT, UPDATE ON ayo.persistence_idempotency_records
                    TO ayo_runtime;
                REVOKE DELETE, TRUNCATE ON ayo.persistence_idempotency_records
                    FROM ayo_runtime;
            END IF;
        END
        $ayo$
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive persistence-history downgrade is prohibited after activation. "
        "Apply a reviewed forward fix or restore a verified backup."
    )
