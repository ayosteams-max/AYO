"""Wallet Foundation.

Revision ID: 20260717_0024
Revises: 20260717_0023
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0024"
down_revision: str | Sequence[str] | None = "20260717_0023"
branch_labels = None
depends_on = None
TABLES = (
    "wallet_accounts",
    "wallet_lineage_entries",
    "wallet_idempotency",
    "wallet_events",
    "wallet_outbox",
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
            "9c",
            "wallet.event.consume",
            "Consume an authoritative financial lineage event into immutable wallet history.",
        ),
        (
            "9d",
            "wallet.account.read_own",
            "Read own ETB wallet balances and immutable history.",
        ),
        (
            "9e",
            "wallet.trace.read",
            "Read immutable wallet lineage and replay-safe event projections.",
        ),
        (
            "9f",
            "support.wallet.read_status",
            "Read wallet status without mutation authority.",
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
    GRANT SELECT, INSERT ON ayo.wallet_accounts, ayo.wallet_lineage_entries,
      ayo.wallet_idempotency, ayo.wallet_events, ayo.wallet_outbox TO ayo_runtime;
    GRANT UPDATE ON ayo.wallet_accounts, ayo.wallet_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'wallet.%' OR code = 'support.wallet.read_status')"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code LIKE 'wallet.%' OR code = 'support.wallet.read_status'"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
