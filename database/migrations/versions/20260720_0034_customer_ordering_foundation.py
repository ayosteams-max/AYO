"""Add universal customer ordering foundation.

Revision ID: 20260720_0034
Revises: 20260720_0033
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0034"
down_revision: str | Sequence[str] | None = "20260720_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    jsonb = postgresql.JSONB()
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
                "permission_id": UUID("00000000-0000-4000-8000-00000000f101"),
                "code": "ordering.create_own",
                "description": "Create an owned canonical commerce order.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f102"),
                "code": "ordering.read_own",
                "description": "Read an owned canonical commerce order.",
                "created_at": now,
            },
        ],
    )
    op.create_table(
        "commerce_orders",
        sa.Column("order_id", sa.UUID(), primary_key=True),
        sa.Column(
            "customer_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("merchant_display_name", sa.String(120), nullable=False),
        sa.Column("merchant_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(63), nullable=False),
        sa.Column("pricing_evidence", jsonb, nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_commerce_order_customer",
        "commerce_orders",
        ["customer_identity_id", "created_at", "order_id"],
        schema="ayo",
    )
    op.create_table(
        "commerce_order_lines",
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            primary_key=True,
        ),
        sa.Column("line_number", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("item_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("category_id", sa.UUID()),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.CheckConstraint(
            "quantity > 0 AND quantity <= 99", name="commerce_line_quantity"
        ),
        sa.CheckConstraint(
            "unit_price_minor >= 0 AND line_total_minor >= 0",
            name="commerce_line_money",
        ),
        schema="ayo",
    )
    op.create_table(
        "commerce_order_evidence",
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            primary_key=True,
        ),
        sa.Column("immutable_payload", jsonb, nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "commerce_order_idempotency",
        sa.Column("customer_identity_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "customer_identity_id",
            "idempotency_key",
            name="uq_commerce_order_idempotency",
        ),
        schema="ayo",
    )
    op.create_table(
        "commerce_order_outbox",
        sa.Column("message_id", sa.UUID(), primary_key=True),
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column("safe_payload", jsonb, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.commerce_orders, ayo.commerce_order_lines, ayo.commerce_order_evidence, ayo.commerce_order_idempotency, ayo.commerce_order_outbox TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "commerce_order_outbox",
        "commerce_order_idempotency",
        "commerce_order_evidence",
        "commerce_order_lines",
        "commerce_orders",
    ):
        op.drop_table(table, schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('ordering.create_own', 'ordering.read_own')"
    )
