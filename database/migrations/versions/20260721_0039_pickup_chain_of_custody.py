"""Add pickup verification and chain of custody.

Revision ID: 20260721_0039
Revises: 20260721_0038
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0039"
down_revision: str | Sequence[str] | None = "20260721_0038"
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
                "permission_id": UUID("00000000-0000-4000-8000-00000000f601"),
                "code": "custody.read_own_merchant",
                "description": "Read custody for an owned merchant order.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f602"),
                "code": "custody.release_own_merchant",
                "description": "Seal and release an owned merchant order.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f603"),
                "code": "custody.accept_assigned",
                "description": "Verify pickup and accept assigned custody.",
                "created_at": now,
            },
        ],
    )
    op.create_table(
        "commerce_custody_records",
        sa.Column("custody_id", sa.UUID(), primary_key=True),
        sa.Column(
            "pickup_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_courier_pickups.pickup_id"),
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
            "courier_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_method", sa.String(20)),
        sa.Column("merchant_released_at", sa.DateTime(timezone=True)),
        sa.Column("custody_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('waiting_for_pickup','order_sealed','pickup_verified','merchant_released','courier_custody_accepted')",
            name="custody_state_valid",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_custody_merchant_state",
        "commerce_custody_records",
        ["merchant_id", "state", "updated_at"],
        schema="ayo",
    )
    op.create_table(
        "commerce_custody_challenges",
        sa.Column("challenge_id", sa.UUID(), primary_key=True),
        sa.Column(
            "custody_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_custody_records.custody_id"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_custody_challenge_active",
        "commerce_custody_challenges",
        ["custody_id", "expires_at"],
        schema="ayo",
    )
    op.create_table(
        "commerce_custody_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column(
            "custody_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_custody_records.custody_id"),
            nullable=False,
        ),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("from_state", sa.String(40), nullable=False),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column(
            "actor_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_custody_event",
        "commerce_custody_events",
        ["custody_id", "version"],
        schema="ayo",
    )
    op.create_table(
        "commerce_custody_idempotency",
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("custody_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_version", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_identity_id", "idempotency_key", name="uq_custody_idempotency"
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ayo.commerce_custody_records, ayo.commerce_custody_challenges TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.commerce_custody_events, ayo.commerce_custody_idempotency TO ayo_runtime"
    )
    op.execute(
        "GRANT UPDATE (response_version) ON ayo.commerce_custody_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "commerce_custody_idempotency",
        "commerce_custody_events",
        "commerce_custody_challenges",
        "commerce_custody_records",
    ):
        op.drop_table(table, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'custody.%'")
