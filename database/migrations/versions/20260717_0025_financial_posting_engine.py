"""Financial Posting Engine.

Revision ID: 20260717_0025
Revises: 20260717_0024
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0025"
down_revision: str | Sequence[str] | None = "20260717_0024"
branch_labels = None
depends_on = None
TABLES = (
    "financial_postings",
    "financial_posting_lines",
    "financial_posting_idempotency",
    "financial_posting_events",
    "financial_posting_outbox",
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
            "a0",
            "financial.posting.create",
            "Create an immutable balanced financial posting from authoritative lineage.",
        ),
        (
            "a1",
            "financial.posting.trace.read",
            "Read immutable financial posting traces and replay-safe views.",
        ),
        (
            "a2",
            "support.financial_posting.read_status",
            "Read financial posting status without mutation authority.",
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
    GRANT SELECT, INSERT ON ayo.financial_postings, ayo.financial_posting_lines,
      ayo.financial_posting_idempotency, ayo.financial_posting_events,
      ayo.financial_posting_outbox TO ayo_runtime;
    GRANT UPDATE ON ayo.financial_posting_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'financial.posting.%' OR code = 'support.financial_posting.read_status')"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code LIKE 'financial.posting.%' OR code = 'support.financial_posting.read_status'"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
