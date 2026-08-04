"""P2 AYO Eat Increment 3 canonical Preparation lifecycle.

Revision ID: 20260723_0054
Revises: 20260723_0053
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260723_0054"
down_revision: str | Sequence[str] | None = "20260723_0053"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "preparation_staff_authorities",
    "preparation_cases",
    "preparation_evidence",
    "preparation_idempotency",
    "preparation_outbox",
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
                "permission_id": UUID("10000000-0000-4000-8000-000000000059"),
                "code": "merchant_preparation.admit",
                "description": "Admit accepted orders into PRE-PRODUCTION canonical Preparation.",
                "created_at": now,
            },
            {
                "permission_id": UUID("10000000-0000-4000-8000-000000000060"),
                "code": "merchant_preparation.observe_overdue",
                "description": "Record PRE-PRODUCTION preparation overdue evidence.",
                "created_at": now,
            },
        ],
    )
    op.execute("""
        CREATE FUNCTION ayo.reject_preparation_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'preparation evidence is append-only';
        END $$;
        CREATE TRIGGER trg_preparation_evidence_immutable
          BEFORE UPDATE OR DELETE ON ayo.preparation_evidence
          FOR EACH ROW EXECUTE FUNCTION
          ayo.reject_preparation_evidence_mutation();
        GRANT SELECT ON ayo.preparation_staff_authorities TO ayo_runtime;
        GRANT SELECT, INSERT, UPDATE ON
          ayo.preparation_cases, ayo.preparation_idempotency TO ayo_runtime;
        GRANT SELECT, INSERT ON
          ayo.preparation_evidence, ayo.preparation_outbox TO ayo_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS trg_preparation_evidence_immutable
          ON ayo.preparation_evidence;
        DROP FUNCTION IF EXISTS ayo.reject_preparation_evidence_mutation();
        DELETE FROM ayo.permissions
        WHERE code IN ('merchant_preparation.admit',
                       'merchant_preparation.observe_overdue');
    """)
    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
