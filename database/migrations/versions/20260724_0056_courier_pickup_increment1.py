"""Courier Pickup Increment 1 assignment attempts and immutable evidence.

Revision ID: 20260724_0056
Revises: 20260723_0055
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0056"
down_revision: str | Sequence[str] | None = "20260723_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_courier_pickup_idempotency",
        "commerce_courier_pickup_idempotency",
        schema="ayo",
        type_="unique",
    )
    op.add_column(
        "commerce_courier_pickup_idempotency",
        sa.Column("action", sa.String(48), nullable=False, server_default="legacy"),
        schema="ayo",
    )
    op.create_unique_constraint(
        "uq_courier_pickup_actor_action_idempotency",
        "commerce_courier_pickup_idempotency",
        ["actor_identity_id", "action", "idempotency_key"],
        schema="ayo",
    )

    op.drop_constraint(
        "commerce_courier_pickups_dispatch_id_key",
        "commerce_courier_pickups",
        schema="ayo",
        type_="unique",
    )
    op.drop_constraint(
        "commerce_courier_pickups_order_id_key",
        "commerce_courier_pickups",
        schema="ayo",
        type_="unique",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column(
            "assignment_id",
            sa.UUID(),
            sa.ForeignKey("ayo.courier_dispatch_assignments.assignment_id"),
        ),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column(
            "assignment_version", sa.Integer(), nullable=False, server_default="1"
        ),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column(
            "policy_code",
            sa.String(80),
            nullable=False,
            server_default="AYO_COURIER_PICKUP_POLICY_V1",
        ),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column("terminal_reason", sa.String(80)),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickups",
        sa.Column("custody_accepted_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    op.create_unique_constraint(
        "uq_courier_pickup_assignment",
        "commerce_courier_pickups",
        ["assignment_id"],
        schema="ayo",
    )
    op.drop_constraint(
        "ck_commerce_courier_pickups_courier_pickup_state_valid",
        "commerce_courier_pickups",
        schema="ayo",
        type_="check",
    )
    op.create_check_constraint(
        "courier_pickup_state_valid",
        "commerce_courier_pickups",
        "state IN ('courier_assigned','travelling_to_merchant',"
        "'arrived_at_merchant','waiting_for_pickup',"
        "'pickup_attempt_ended_before_custody')",
        schema="ayo",
    )
    op.create_check_constraint(
        "courier_pickup_policy_version_positive",
        "commerce_courier_pickups",
        "policy_version >= 1 AND assignment_version >= 1 AND attempt_number >= 1",
        schema="ayo",
    )

    op.add_column(
        "commerce_courier_pickup_events",
        sa.Column("correlation_id", sa.UUID()),
        schema="ayo",
    )
    op.add_column(
        "commerce_courier_pickup_events",
        sa.Column("causation_id", sa.UUID()),
        schema="ayo",
    )
    op.create_table(
        "commerce_courier_pickup_evidence",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "pickup_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_courier_pickups.pickup_id"),
            nullable=False,
        ),
        sa.Column("pickup_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("actor_identity_id", sa.UUID()),
        sa.Column("acting_for_identity_id", sa.UUID()),
        sa.Column("merchant_id", sa.UUID()),
        sa.Column("authority_basis", sa.String(128)),
        sa.Column("source_reference", sa.UUID()),
        sa.Column("source_version", sa.Integer()),
        sa.Column("reason", sa.String(80)),
        sa.Column("waiting_duration_seconds", sa.Integer()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.UUID(), nullable=False),
        sa.Column("causation_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "waiting_duration_seconds IS NULL OR waiting_duration_seconds >= 0",
            name="courier_pickup_evidence_wait_nonnegative",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_courier_pickup_evidence_attempt",
        "commerce_courier_pickup_evidence",
        ["pickup_id", "pickup_version"],
        schema="ayo",
    )

    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f504"),
                "code": "courier_pickup.correct_assigned",
                "description": "Correct assigned courier arrival evidence append-only.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f505"),
                "code": "courier_pickup.close_assigned",
                "description": "End an assigned Pickup attempt before custody.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f506"),
                "code": "courier_pickup.correct_own_merchant",
                "description": "Correct merchant acknowledgement evidence append-only.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f507"),
                "code": "courier_pickup.close_own_merchant",
                "description": "End an owned-merchant Pickup attempt before custody.",
                "created_at": now,
            },
        ],
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.commerce_courier_pickup_evidence TO ayo_runtime"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS ("
        "SELECT 1 FROM ayo.commerce_courier_pickups GROUP BY order_id HAVING count(*) > 1"
        ") THEN RAISE EXCEPTION 'cannot downgrade: multiple Pickup attempts exist'; "
        "END IF; END $$"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN "
        "('courier_pickup.correct_assigned','courier_pickup.close_assigned',"
        "'courier_pickup.correct_own_merchant','courier_pickup.close_own_merchant')"
    )
    op.drop_table("commerce_courier_pickup_evidence", schema="ayo")
    op.drop_column("commerce_courier_pickup_events", "causation_id", schema="ayo")
    op.drop_column("commerce_courier_pickup_events", "correlation_id", schema="ayo")
    op.drop_constraint(
        "ck_commerce_courier_pickups_courier_pickup_policy_version_positive",
        "commerce_courier_pickups",
        schema="ayo",
        type_="check",
    )
    op.drop_constraint(
        "ck_commerce_courier_pickups_courier_pickup_state_valid",
        "commerce_courier_pickups",
        schema="ayo",
        type_="check",
    )
    op.create_check_constraint(
        "courier_pickup_state_valid",
        "commerce_courier_pickups",
        "state IN ('courier_assigned','travelling_to_merchant',"
        "'arrived_at_merchant','waiting_for_pickup')",
        schema="ayo",
    )
    op.drop_constraint(
        "uq_courier_pickup_assignment",
        "commerce_courier_pickups",
        schema="ayo",
        type_="unique",
    )
    for column in (
        "custody_accepted_at",
        "terminal_reason",
        "policy_version",
        "policy_code",
        "attempt_number",
        "assignment_version",
        "assignment_id",
    ):
        op.drop_column("commerce_courier_pickups", column, schema="ayo")
    op.create_unique_constraint(
        "commerce_courier_pickups_order_id_key",
        "commerce_courier_pickups",
        ["order_id"],
        schema="ayo",
    )
    op.create_unique_constraint(
        "commerce_courier_pickups_dispatch_id_key",
        "commerce_courier_pickups",
        ["dispatch_id"],
        schema="ayo",
    )
    op.drop_constraint(
        "uq_courier_pickup_actor_action_idempotency",
        "commerce_courier_pickup_idempotency",
        schema="ayo",
        type_="unique",
    )
    op.drop_column("commerce_courier_pickup_idempotency", "action", schema="ayo")
    op.create_unique_constraint(
        "uq_courier_pickup_idempotency",
        "commerce_courier_pickup_idempotency",
        ["actor_identity_id", "idempotency_key"],
        schema="ayo",
    )
