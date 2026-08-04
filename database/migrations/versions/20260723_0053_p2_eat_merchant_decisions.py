"""Add P2 AYO Eat Increment 2 merchant decision lifecycle.

Revision ID: 20260723_0053
Revises: 20260723_0052
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260723_0053"
down_revision: str | Sequence[str] | None = "20260723_0052"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "merchant_staff_decision_authorities",
    "merchant_decision_cases",
    "merchant_decision_evidence",
    "merchant_decision_idempotency",
    "merchant_decision_outbox",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in NEW_TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)

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
                "permission_id": UUID("10000000-0000-4000-8000-000000000057"),
                "code": "merchant_orders.admit_decision",
                "description": "Admit PRE-PRODUCTION merchant decision cases.",
                "created_at": now,
            },
            {
                "permission_id": UUID("10000000-0000-4000-8000-000000000058"),
                "code": "merchant_orders.expire_decisions",
                "description": "Expire due PRE-PRODUCTION merchant decision cases.",
                "created_at": now,
            },
        ],
    )
    op.execute(
        """
        CREATE FUNCTION ayo.reject_merchant_decision_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'merchant decision evidence is append-only';
        END $$;
        CREATE TRIGGER trg_merchant_decision_evidence_immutable
          BEFORE UPDATE OR DELETE ON ayo.merchant_decision_evidence
          FOR EACH ROW EXECUTE FUNCTION
          ayo.reject_merchant_decision_evidence_mutation();
        """
    )
    op.execute(
        """
        GRANT SELECT ON
          ayo.merchant_staff_decision_authorities
        TO ayo_runtime;
        GRANT SELECT, INSERT, UPDATE ON
          ayo.merchant_decision_cases,
          ayo.merchant_decision_idempotency
        TO ayo_runtime;
        GRANT SELECT, INSERT ON
          ayo.merchant_decision_evidence,
          ayo.merchant_decision_outbox
        TO ayo_runtime;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_merchant_decision_evidence_immutable
          ON ayo.merchant_decision_evidence;
        DROP FUNCTION IF EXISTS ayo.reject_merchant_decision_evidence_mutation();
        """
    )
    for name in reversed(NEW_TABLES):
        op.drop_table(name, schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN "
        "('merchant_orders.admit_decision','merchant_orders.expire_decisions')"
    )
