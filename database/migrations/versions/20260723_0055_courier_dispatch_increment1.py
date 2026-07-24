"""Courier Dispatch Increment 1 lifecycle and immutable evidence.

Revision ID: 20260723_0055
Revises: 20260723_0054
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260723_0055"
down_revision: str | Sequence[str] | None = "20260723_0054"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "courier_dispatch_offers",
    "courier_dispatch_assignments",
    "courier_dispatch_evidence",
)


def upgrade() -> None:
    op.add_column(
        "commerce_courier_dispatch_requests",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="0"),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_dispatch_requests",
        sa.Column("active_offer_id", sa.UUID()),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_dispatch_requests",
        sa.Column("active_assignment_id", sa.UUID()),
        schema="ayo",
    )
    op.drop_constraint(
        "ck_commerce_courier_dispatch_requests_courier_dispatch_state_valid",
        "commerce_courier_dispatch_requests",
        schema="ayo",
        type_="check",
    )
    op.create_check_constraint(
        "courier_dispatch_state_valid",
        "commerce_courier_dispatch_requests",
        "state IN ('waiting_for_courier','courier_offered','courier_assigned',"
        "'dispatch_cancelled','dispatch_unfulfilled')",
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_dispatch_events",
        sa.Column("correlation_id", sa.UUID()),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_dispatch_events",
        sa.Column("causation_id", sa.UUID()),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_dispatch_idempotency",
        sa.Column(
            "operation",
            sa.String(40),
            nullable=False,
            server_default="legacy",
        ),
        schema="ayo",
    )
    op.drop_constraint(
        "uq_courier_dispatch_idempotency",
        "commerce_courier_dispatch_idempotency",
        schema="ayo",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_courier_dispatch_actor_action_idempotency",
        "commerce_courier_dispatch_idempotency",
        ["actor_identity_id", "operation", "idempotency_key"],
        schema="ayo",
    )
    bind = op.get_bind()
    for name in NEW_TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)

    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID("10000000-0000-4000-8000-000000000062"),
                "code": "courier_dispatch.admit",
                "description": (
                    "Admit valid Preparation readiness evidence into PRE-PRODUCTION "
                    "Courier Dispatch."
                ),
                "created_at": datetime.now(UTC),
            },
            {
                "permission_id": UUID("10000000-0000-4000-8000-000000000061"),
                "code": "courier_dispatch.manage",
                "description": (
                    "Manage PRE-PRODUCTION courier offers, assignment recovery, "
                    "cancellation and unfulfilled outcomes."
                ),
                "created_at": datetime.now(UTC),
            },
        ],
    )
    op.execute("""
        CREATE FUNCTION ayo.reject_courier_dispatch_immutable_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'courier dispatch evidence is append-only';
        END $$;
        CREATE TRIGGER trg_courier_dispatch_evidence_immutable
          BEFORE UPDATE OR DELETE ON ayo.courier_dispatch_evidence
          FOR EACH ROW EXECUTE FUNCTION
          ayo.reject_courier_dispatch_immutable_mutation();
        CREATE TRIGGER trg_courier_dispatch_events_immutable
          BEFORE UPDATE OR DELETE ON ayo.commerce_courier_dispatch_events
          FOR EACH ROW EXECUTE FUNCTION
          ayo.reject_courier_dispatch_immutable_mutation();
        GRANT SELECT, INSERT, UPDATE ON
          ayo.courier_dispatch_offers,
          ayo.courier_dispatch_assignments TO ayo_runtime;
        GRANT SELECT, INSERT ON
          ayo.courier_dispatch_evidence TO ayo_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS trg_courier_dispatch_evidence_immutable
          ON ayo.courier_dispatch_evidence;
        DROP TRIGGER IF EXISTS trg_courier_dispatch_events_immutable
          ON ayo.commerce_courier_dispatch_events;
        DROP FUNCTION IF EXISTS ayo.reject_courier_dispatch_immutable_mutation();
        DELETE FROM ayo.permissions
        WHERE code IN ('courier_dispatch.manage','courier_dispatch.admit');
    """)
    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
    op.drop_constraint(
        "uq_courier_dispatch_actor_action_idempotency",
        "commerce_courier_dispatch_idempotency",
        schema="ayo",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_courier_dispatch_idempotency",
        "commerce_courier_dispatch_idempotency",
        ["actor_identity_id", "idempotency_key"],
        schema="ayo",
    )
    op.drop_column("commerce_courier_dispatch_idempotency", "operation", schema="ayo")
    op.drop_column("commerce_courier_dispatch_events", "causation_id", schema="ayo")
    op.drop_column("commerce_courier_dispatch_events", "correlation_id", schema="ayo")
    op.drop_constraint(
        "ck_commerce_courier_dispatch_requests_courier_dispatch_state_valid",
        "commerce_courier_dispatch_requests",
        schema="ayo",
        type_="check",
    )
    op.create_check_constraint(
        "courier_dispatch_state_valid",
        "commerce_courier_dispatch_requests",
        "state IN ('waiting_for_courier','courier_offered','courier_assigned')",
        schema="ayo",
    )
    op.drop_column(
        "commerce_courier_dispatch_requests", "active_assignment_id", schema="ayo"
    )
    op.drop_column(
        "commerce_courier_dispatch_requests", "active_offer_id", schema="ayo"
    )
    op.drop_column("commerce_courier_dispatch_requests", "attempt_number", schema="ayo")
