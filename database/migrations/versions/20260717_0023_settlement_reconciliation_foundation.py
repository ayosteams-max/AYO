"""Settlement & Financial Reconciliation Foundation.

Revision ID: 20260717_0023
Revises: 20260717_0022
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0023"
down_revision: str | Sequence[str] | None = "20260717_0022"
branch_labels = None
depends_on = None
TABLES = (
    "settlement_batches",
    "settlement_items",
    "reconciliation_records",
    "reconciliation_exceptions",
    "settlement_events",
    "settlement_outbox",
    "settlement_idempotency",
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
            "95",
            "settlement.batch.create",
            "Create an immutable settlement reconciliation batch.",
        ),
        (
            "96",
            "settlement.collect.run",
            "Collect provider-neutral batch items for reconciliation.",
        ),
        (
            "97",
            "settlement.reconcile.run",
            "Run bounded reconciliation and exception classification.",
        ),
        (
            "98",
            "settlement.ready.approve",
            "Approve a balanced batch for settlement readiness.",
        ),
        (
            "99",
            "settlement.exception.investigate",
            "Investigate reconciliation exceptions and record manual review outcomes.",
        ),
        (
            "9a",
            "settlement.trace.read",
            "Read immutable settlement and reconciliation traces.",
        ),
        (
            "9b",
            "support.settlement.read_status",
            "Read settlement and reconciliation status without mutation authority.",
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
    GRANT SELECT, INSERT ON ayo.settlement_batches, ayo.settlement_items,
      ayo.reconciliation_records, ayo.reconciliation_exceptions,
      ayo.settlement_events, ayo.settlement_outbox, ayo.settlement_idempotency TO ayo_runtime;
    GRANT UPDATE ON ayo.settlement_batches, ayo.settlement_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'settlement.%' OR code = 'support.settlement.read_status')"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code LIKE 'settlement.%' OR code = 'support.settlement.read_status'"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
