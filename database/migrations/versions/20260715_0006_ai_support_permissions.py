"""Register authorization-ready AI support permissions.

Revision ID: 20260715_0006
Revises: 20260715_0005
Create Date: 2026-07-15

This revision creates no identity, role assignment, provider or AI workload.
It is immutable after application to any shared environment.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0006"
down_revision: str | Sequence[str] | None = "20260715_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "ayo"


def upgrade() -> None:
    registered_at = datetime.now(UTC)
    permissions_table = sa.table(
        "permissions",
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-0000000000{index}",
                "code": code,
                "description": description,
                "created_at": registered_at,
            }
            for index, (code, description) in enumerate(
                (
                    (
                        "support.case.create",
                        "Create a support case with approved structured details.",
                    ),
                    (
                        "support.case.read_assigned",
                        "Read only support cases assigned to the service identity.",
                    ),
                    (
                        "support.case.update",
                        "Update approved fields on an assigned support case.",
                    ),
                    (
                        "support.case.escalate",
                        "Escalate a support case to trained human support.",
                    ),
                    (
                        "support.trip.read_limited",
                        "Read the minimum approved trip support view.",
                    ),
                    (
                        "support.payment.read_status",
                        "Read payment status without credentials or mutation authority.",
                    ),
                    (
                        "support.account.read_limited",
                        "Read the minimum approved account support view.",
                    ),
                    (
                        "support.guidance.provide",
                        "Provide approved low-risk support guidance.",
                    ),
                ),
                start=10,
            )
        ],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Deleting authorization permissions can invalidate reviewed policy. Apply "
        "a forward fix instead."
    )
