"""Add scheduled integration pickup verification authority.

Revision ID: 20260716_0012
Revises: 20260716_0011
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260716_0012"
down_revision: str | Sequence[str] | None = "20260716_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.tables["ayo.reservation_pickup_verifications"].create(op.get_bind())
    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON ayo.reservation_pickup_verifications TO ayo_runtime;
        END IF; END $$"""
    )
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
            "34",
            "scheduled.rider.create",
            "Create a scheduled reservation as the authenticated booker.",
        ),
        ("35", "scheduled.reservation.read", "Read an owned scheduled reservation."),
        (
            "36",
            "scheduled.reservation.manage",
            "Update, confirm or cancel an owned reservation.",
        ),
        (
            "37",
            "scheduled.driver.commitment.respond",
            "Respond to an authenticated driver's commitment.",
        ),
        (
            "38",
            "scheduled.support.handoff",
            "Create an authorized assisted-booking support handoff.",
        ),
        ("39", "scheduled.worker.run", "Run bounded scheduled-dispatch workers."),
        ("40", "scheduled.worker.health.read", "Read scheduled worker health."),
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


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM ayo.permissions WHERE code LIKE 'scheduled.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'scheduled.%'")
    metadata.tables["ayo.reservation_pickup_verifications"].drop(op.get_bind())
