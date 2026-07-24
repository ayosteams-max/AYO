"""Payment Orchestration Foundation.

Revision ID: 20260717_0021
Revises: 20260717_0020
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0021"
down_revision: str | Sequence[str] | None = "20260717_0020"
branch_labels = None
depends_on = None
TABLES = (
    "payment_intents",
    "payment_attempts",
    "payment_callback_envelopes",
    "payment_idempotency",
    "payment_events",
    "payment_outbox",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)

    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    values = (
        (
            "81",
            "payment.intent.create",
            "Create a provider-neutral payment intent for an owned ride.",
        ),
        (
            "82",
            "payment.intent.read_own",
            "Read owned payment intent and attempt status.",
        ),
        (
            "83",
            "payment.attempt.execute",
            "Execute a provider-neutral payment attempt transition.",
        ),
        (
            "84",
            "payment.callback.ingest",
            "Ingest a verified provider callback envelope with replay protection.",
        ),
        (
            "85",
            "payment.reconciliation.run",
            "Run bounded payment reconciliation transitions for outcome_unknown attempts.",
        ),
        (
            "86",
            "payment.trace.read",
            "Read immutable payment traceability, events and replay views.",
        ),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-0000000000{suffix}",
                "code": code,
                "description": description,
                "created_at": datetime.now(UTC),
            }
            for suffix, code, description in values
        ],
    )

    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
    GRANT SELECT, INSERT ON ayo.payment_intents, ayo.payment_attempts,
      ayo.payment_callback_envelopes, ayo.payment_idempotency,
      ayo.payment_events, ayo.payment_outbox TO ayo_runtime;
    GRANT UPDATE ON ayo.payment_attempts, ayo.payment_callback_envelopes,
      ayo.payment_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'payment.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'payment.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
