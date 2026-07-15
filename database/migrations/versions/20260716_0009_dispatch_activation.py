"""Add reversible outbox dead-letter state for controlled dispatch activation.

Revision ID: 20260716_0009
Revises: 20260716_0008
Create Date: 2026-07-16
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0009"
down_revision: str | Sequence[str] | None = "20260716_0008"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.add_column(
        "dispatch_outbox",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_dispatch_outbox_pending",
        table_name="dispatch_outbox",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dispatch_outbox_pending",
        "dispatch_outbox",
        ["available_at", "occurred_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NULL AND dead_lettered_at IS NULL"),
    )
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": "00000000-0000-4000-8000-000000000033",
                "code": "dispatch.admin.health.read",
                "description": "Read internal dispatch worker health.",
                "created_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM ayo.permissions WHERE "
        "code='dispatch.admin.health.read')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code='dispatch.admin.health.read'")
    op.drop_index(
        "ix_dispatch_outbox_pending",
        table_name="dispatch_outbox",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dispatch_outbox_pending",
        "dispatch_outbox",
        ["available_at", "occurred_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_column("dispatch_outbox", "dead_lettered_at", schema=SCHEMA)
