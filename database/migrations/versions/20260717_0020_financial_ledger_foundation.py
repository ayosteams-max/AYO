"""Financial Ledger Foundation.

Revision ID: 20260717_0020
Revises: 20260716_0019
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0020"
down_revision: str | Sequence[str] | None = "20260716_0019"
branch_labels = None
depends_on = None
TABLES = (
    "ledger_books",
    "ledger_accounts",
    "ledger_journals",
    "ledger_entries",
    "ledger_idempotency",
    "ledger_events",
    "ledger_outbox",
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
            "71",
            "ledger.book.manage",
            "Create and archive immutable ledger books and accounts.",
        ),
        ("72", "ledger.journal.post", "Post an immutable balanced ledger journal."),
        (
            "73",
            "ledger.journal.compensate",
            "Post a compensating ledger journal linked to a predecessor.",
        ),
        (
            "74",
            "ledger.trace.read",
            "Read immutable ledger traceability and replay projections.",
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
    GRANT SELECT, INSERT ON ayo.ledger_books, ayo.ledger_accounts, ayo.ledger_journals,
      ayo.ledger_entries, ayo.ledger_idempotency, ayo.ledger_events, ayo.ledger_outbox TO ayo_runtime;
    GRANT UPDATE ON ayo.ledger_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'ledger.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'ledger.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
