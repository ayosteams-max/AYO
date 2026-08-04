"""Financial Control & Holds Engine.

Revision ID: 20260717_0026
Revises: 20260717_0025
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0026"
down_revision: str | Sequence[str] | None = "20260717_0025"
branch_labels = None
depends_on = None
TABLES = (
    "financial_holds",
    "financial_hold_state_history",
    "financial_hold_idempotency",
    "financial_hold_events",
    "financial_hold_outbox",
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
            "b0",
            "financial.hold.create",
            "Create a financial hold that can block future money movement.",
        ),
        (
            "b1",
            "financial.hold.review",
            "Move a financial hold into or out of under-review state.",
        ),
        (
            "b2",
            "financial.hold.release",
            "Release a financial hold and allow future execution paths.",
        ),
        (
            "b3",
            "financial.hold.escalate",
            "Escalate a financial hold for higher-authority manual review.",
        ),
        (
            "b4",
            "financial.hold.expire",
            "Expire a financial hold based on authorized control policy.",
        ),
        (
            "b5",
            "financial.hold.cancel",
            "Cancel a financial hold before release when justified.",
        ),
        (
            "b6",
            "financial.hold.trace.read",
            "Read immutable financial hold traces and replay-safe views.",
        ),
        (
            "b7",
            "support.financial_hold.read_status",
            "Read financial hold status without mutation authority.",
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
    GRANT SELECT, INSERT ON ayo.financial_holds, ayo.financial_hold_state_history,
      ayo.financial_hold_idempotency, ayo.financial_hold_events,
      ayo.financial_hold_outbox TO ayo_runtime;
    GRANT UPDATE ON ayo.financial_holds, ayo.financial_hold_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'financial.hold.%' OR code = 'support.financial_hold.read_status')"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code LIKE 'financial.hold.%' OR code = 'support.financial_hold.read_status'"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
