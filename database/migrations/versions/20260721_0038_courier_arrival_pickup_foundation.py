"""Add courier arrival and pickup-waiting foundation.

Revision ID: 20260721_0038
Revises: 20260721_0037
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0038"
down_revision: str | Sequence[str] | None = "20260721_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
                "permission_id": UUID("00000000-0000-4000-8000-00000000f501"),
                "code": "courier_pickup.read_own_merchant",
                "description": "Read courier arrival evidence for an owned merchant order.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f502"),
                "code": "courier_pickup.acknowledge_own_merchant",
                "description": "Acknowledge courier arrival for an owned merchant order.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f503"),
                "code": "courier_pickup.manage_assigned",
                "description": "Manage arrival state as the assigned courier.",
                "created_at": now,
            },
        ],
    )
    op.create_table(
        "commerce_courier_pickups",
        sa.Column("pickup_id", sa.UUID(), primary_key=True),
        sa.Column(
            "dispatch_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_courier_dispatch_requests.dispatch_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column(
            "assigned_courier_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("assignment_message_id", sa.UUID(), nullable=False, unique=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("travelling_at", sa.DateTime(timezone=True)),
        sa.Column("arrived_at", sa.DateTime(timezone=True)),
        sa.Column("merchant_acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("waiting_duration_seconds", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('courier_assigned','travelling_to_merchant','arrived_at_merchant','waiting_for_pickup')",
            name="courier_pickup_state_valid",
        ),
        sa.CheckConstraint("version >= 1", name="courier_pickup_version_positive"),
        sa.CheckConstraint(
            "waiting_duration_seconds IS NULL OR waiting_duration_seconds >= 0",
            name="courier_pickup_wait_nonnegative",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_courier_pickup_merchant_state",
        "commerce_courier_pickups",
        ["merchant_id", "state", "updated_at"],
        schema="ayo",
    )
    op.create_table(
        "commerce_courier_pickup_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column(
            "pickup_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_courier_pickups.pickup_id"),
            nullable=False,
        ),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("from_state", sa.String(40)),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column(
            "actor_identity_id", sa.UUID(), sa.ForeignKey("ayo.identities.identity_id")
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_courier_pickup_event",
        "commerce_courier_pickup_events",
        ["pickup_id", "version"],
        schema="ayo",
    )
    op.create_table(
        "commerce_courier_pickup_idempotency",
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("pickup_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_version", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_identity_id", "idempotency_key", name="uq_courier_pickup_idempotency"
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ayo.commerce_courier_pickups TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.commerce_courier_pickup_events, ayo.commerce_courier_pickup_idempotency TO ayo_runtime"
    )
    op.execute(
        "GRANT UPDATE (response_version) ON ayo.commerce_courier_pickup_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "commerce_courier_pickup_idempotency",
        "commerce_courier_pickup_events",
        "commerce_courier_pickups",
    ):
        op.drop_table(table, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'courier_pickup.%'")
