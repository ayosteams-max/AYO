"""Add universal delivery verification and completion.

Revision ID: 20260721_0040
Revises: 20260721_0039
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0040"
down_revision: str | Sequence[str] | None = "20260721_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    p = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        p,
        [
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f701"),
                "code": "delivery.read_own",
                "description": "Read own order delivery credential.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f702"),
                "code": "delivery.manage_assigned",
                "description": "Manage assigned courier delivery.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f703"),
                "code": "delivery.confirm_receipt",
                "description": "Confirm receipt as ordering customer.",
                "created_at": now,
            },
        ],
    )
    op.create_table(
        "commerce_delivery_credentials",
        sa.Column("credential_id", sa.UUID(), primary_key=True),
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_orders.order_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_message_id", sa.UUID(), nullable=False, unique=True),
        sa.Column("order_number", sa.String(32), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "commerce_deliveries",
        sa.Column("delivery_id", sa.UUID(), primary_key=True),
        sa.Column(
            "custody_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_custody_records.custody_id"),
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
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("courier_identity_id", sa.UUID(), nullable=False),
        sa.Column(
            "credential_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_delivery_credentials.credential_id"),
            nullable=False,
        ),
        sa.Column("source_message_id", sa.UUID(), nullable=False, unique=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("arriving_at", sa.DateTime(timezone=True)),
        sa.Column("customer_available_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_method", sa.String(20)),
        sa.Column("customer_received_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('courier_arriving','customer_available','delivery_verified','customer_received','courier_delivery_completed','chain_of_custody_closed')",
            name="delivery_state_valid",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_delivery_courier_state",
        "commerce_deliveries",
        ["courier_identity_id", "state", "updated_at"],
        schema="ayo",
    )
    op.create_table(
        "commerce_delivery_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column(
            "delivery_id",
            sa.UUID(),
            sa.ForeignKey("ayo.commerce_deliveries.delivery_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(90), nullable=False),
        sa.Column("from_state", sa.String(40)),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("actor_identity_id", sa.UUID()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_delivery_event",
        "commerce_delivery_events",
        ["delivery_id", "version"],
        schema="ayo",
    )
    op.create_table(
        "commerce_delivery_idempotency",
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("delivery_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_version", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_identity_id", "idempotency_key", name="uq_delivery_idempotency"
        ),
        schema="ayo",
    )
    op.create_table(
        "commerce_delivery_reminders",
        sa.Column("reminder_id", sa.UUID(), primary_key=True),
        sa.Column("delivery_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("eta_evidence_id", sa.UUID(), nullable=False),
        sa.Column("eta_minutes", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "delivery_id", "channel", name="uq_delivery_reminder_channel"
        ),
        schema="ayo",
    )
    op.create_table(
        "commerce_delivery_notification_intents",
        sa.Column("intent_id", sa.UUID(), primary_key=True),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("delivery_id", sa.UUID()),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template_code", sa.String(63), nullable=False),
        sa.Column("secure_credential_reference", sa.UUID()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "order_id",
            "channel",
            "template_code",
            name="uq_delivery_notification_intent",
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON ayo.commerce_delivery_credentials,ayo.commerce_deliveries TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT,INSERT ON ayo.commerce_delivery_events,ayo.commerce_delivery_idempotency,ayo.commerce_delivery_reminders,ayo.commerce_delivery_notification_intents TO ayo_runtime"
    )
    op.execute(
        "GRANT UPDATE (response_version) ON ayo.commerce_delivery_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    for t in (
        "commerce_delivery_notification_intents",
        "commerce_delivery_reminders",
        "commerce_delivery_idempotency",
        "commerce_delivery_events",
        "commerce_deliveries",
        "commerce_delivery_credentials",
    ):
        op.drop_table(t, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'delivery.%'")
