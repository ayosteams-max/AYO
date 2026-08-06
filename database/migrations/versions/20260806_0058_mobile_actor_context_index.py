"""Add bounded current-courier pickup lookup index.

Revision ID: 20260806_0058
Revises: 20260805_0057
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0058"
down_revision: str | Sequence[str] | None = "20260805_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_courier_pickup_current_courier",
        "commerce_courier_pickups",
        ["assigned_courier_identity_id", sa.text("updated_at DESC"), "pickup_id"],
        unique=False,
        schema="ayo",
        postgresql_where=sa.text(
            "state IN ('courier_assigned', 'travelling_to_merchant', "
            "'arrived_at_merchant', 'waiting_for_pickup')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_courier_pickup_current_courier",
        table_name="commerce_courier_pickups",
        schema="ayo",
    )
