"""Add merchant order management foundation.

Revision ID: 20260721_0035
Revises: 20260720_0034
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0035"
down_revision: str | Sequence[str] | None = "20260720_0034"
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
                "permission_id": UUID("00000000-0000-4000-8000-00000000f201"),
                "code": "merchant_orders.read_own",
                "description": "Read orders belonging to an owned approved merchant.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f202"),
                "code": "merchant_orders.decide_own",
                "description": "Accept or reject orders belonging to an owned approved merchant.",
                "created_at": now,
            },
        ],
    )
    op.add_column(
        "commerce_orders",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="ayo",
    )
    op.alter_column("commerce_orders", "version", server_default=None, schema="ayo")
    op.create_index(
        "ix_commerce_order_merchant_state",
        "commerce_orders",
        ["merchant_id", "state", "created_at", "order_id"],
        schema="ayo",
    )
    op.create_table(
        "commerce_order_timeline",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            nullable=False,
        ),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column("from_state", sa.String(63)),
        sa.Column("to_state", sa.String(63), nullable=False),
        sa.Column(
            "actor_identity_id", sa.UUID(), sa.ForeignKey("ayo.identities.identity_id")
        ),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("customer_reason_code", sa.String(63)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_commerce_order_timeline",
        "commerce_order_timeline",
        ["order_id", "order_version"],
        schema="ayo",
    )
    op.create_table(
        "commerce_order_rejections",
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            primary_key=True,
        ),
        sa.Column("customer_reason_code", sa.String(63), nullable=False),
        sa.Column("customer_message", sa.String(240), nullable=False),
        sa.Column("internal_merchant_note", sa.String(1000)),
        sa.Column(
            "decided_by_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "commerce_merchant_action_idempotency",
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
            name="uq_commerce_merchant_action_idempotency",
        ),
        schema="ayo",
    )
    op.execute(
        "INSERT INTO ayo.commerce_order_timeline (event_id, order_id, merchant_id, event_type, from_state, to_state, actor_identity_id, order_version, customer_reason_code, occurred_at) SELECT gen_random_uuid(), order_id, merchant_id, 'commerce.order.created', NULL, state, customer_identity_id, 1, NULL, created_at FROM ayo.commerce_orders"
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.commerce_order_timeline, ayo.commerce_order_rejections, ayo.commerce_merchant_action_idempotency TO ayo_runtime"
    )
    op.execute("GRANT UPDATE (state, version) ON ayo.commerce_orders TO ayo_runtime")
    op.execute(
        "GRANT UPDATE (response_version) ON ayo.commerce_merchant_action_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    op.execute("REVOKE UPDATE (state, version) ON ayo.commerce_orders FROM ayo_runtime")
    for table in (
        "commerce_merchant_action_idempotency",
        "commerce_order_rejections",
        "commerce_order_timeline",
    ):
        op.drop_table(table, schema="ayo")
    op.drop_index(
        "ix_commerce_order_merchant_state", table_name="commerce_orders", schema="ayo"
    )
    op.drop_column("commerce_orders", "version", schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('merchant_orders.read_own', 'merchant_orders.decide_own')"
    )
