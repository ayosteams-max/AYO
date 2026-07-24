"""Settlement and reconciliation compatibility evolution.

Revision ID: 20260718_0027
Revises: 20260717_0026
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260718_0027"
down_revision: str | Sequence[str] | None = "20260717_0026"
branch_labels = None
depends_on = None
TABLES = (
    "settlement_approvals",
    "settlement_hold_evidence",
    "settlement_external_evidence",
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
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": "00000000-0000-4000-8000-0000000000b8",
                "code": "settlement.ready.reject",
                "description": "Reject or revoke settlement readiness approval evidence.",
                "created_at": datetime.now(UTC),
            },
            {
                "permission_id": "00000000-0000-4000-8000-0000000000b9",
                "code": "settlement.evidence.record",
                "description": "Record provider-neutral settlement evidence without executing money movement.",
                "created_at": datetime.now(UTC),
            },
        ],
    )
    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
    GRANT SELECT, INSERT ON ayo.settlement_approvals,
      ayo.settlement_hold_evidence, ayo.settlement_external_evidence TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM ayo.permissions WHERE code IN "
        "('settlement.ready.reject','settlement.evidence.record'))"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN "
        "('settlement.ready.reject','settlement.evidence.record')"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
