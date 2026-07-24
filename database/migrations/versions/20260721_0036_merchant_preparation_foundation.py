"""Add merchant preparation foundation.

Revision ID: 20260721_0036
Revises: 20260721_0035
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0036"
down_revision: str | Sequence[str] | None = "20260721_0035"
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
                "permission_id": UUID("00000000-0000-4000-8000-00000000f301"),
                "code": "merchant_preparation.read_own",
                "description": "Read preparation evidence for an owned approved merchant order.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f302"),
                "code": "merchant_preparation.manage_own",
                "description": "Manage preparation for an owned approved merchant order.",
                "created_at": now,
            },
        ],
    )
    op.create_table(
        "commerce_order_preparations",
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            primary_key=True,
        ),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("estimated_ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("latest_delay_reason_code", sa.String(63)),
        sa.Column("latest_delay_message", sa.String(240)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "estimated_duration_seconds >= 60 AND estimated_duration_seconds <= 14400",
            name="commerce_preparation_estimate_bounds",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="commerce_preparation_progress_bounds",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_commerce_preparation_merchant",
        "commerce_order_preparations",
        ["merchant_id", "updated_at", "order_id"],
        schema="ayo",
    )
    op.create_table(
        "commerce_preparation_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            nullable=False,
        ),
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column(
            "actor_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Integer()),
        sa.Column("delay_reason_code", sa.String(63)),
        sa.Column("delay_message", sa.String(240)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_commerce_preparation_event_order",
        "commerce_preparation_events",
        ["order_id", "order_version"],
        schema="ayo",
    )
    op.create_table(
        "commerce_preparation_idempotency",
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_version", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_identity_id",
            "merchant_id",
            "idempotency_key",
            name="uq_commerce_preparation_idempotency",
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ayo.commerce_order_preparations TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.commerce_preparation_events, ayo.commerce_preparation_idempotency TO ayo_runtime"
    )
    op.execute(
        "GRANT UPDATE (response_version) ON ayo.commerce_preparation_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "commerce_preparation_idempotency",
        "commerce_preparation_events",
        "commerce_order_preparations",
    ):
        op.drop_table(table, schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('merchant_preparation.read_own', 'merchant_preparation.manage_own')"
    )
