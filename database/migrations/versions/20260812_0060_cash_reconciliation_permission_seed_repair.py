"""Seed cash reconciliation execute permission for RBAC parity.

Revision ID: 20260812_0060
Revises: 20260811_0059
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0060"
down_revision: str | Sequence[str] | None = "20260811_0059"
branch_labels = None
depends_on = None

_PERMISSION_ID = UUID("00000000-0000-4000-8000-00000000d005")
_PERMISSION_CODE = "cash.reconciliation.execute"
_PERMISSION_DESCRIPTION = "Clear a cash obligation from authorized remittance evidence."


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO ayo.permissions (permission_id, code, description, created_at)
            VALUES (:permission_id, :code, :description, :created_at)
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "permission_id": _PERMISSION_ID,
            "code": _PERMISSION_CODE,
            "description": _PERMISSION_DESCRIPTION,
            "created_at": datetime.now(UTC),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM ayo.role_permissions
            WHERE permission_id IN (
                SELECT permission_id
                FROM ayo.permissions
                WHERE code = :code
            )
            """
        ),
        {"code": _PERMISSION_CODE},
    )
    bind.execute(
        sa.text("DELETE FROM ayo.permissions WHERE code = :code"),
        {"code": _PERMISSION_CODE},
    )
