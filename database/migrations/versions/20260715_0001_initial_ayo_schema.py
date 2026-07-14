"""Create the initial AYO application schema.

Revision ID: 20260715_0001
Revises: None
Create Date: 2026-07-15

This reviewed initial revision is immutable after application to any shared
environment. Corrections require a new forward migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ayo"


def upgrade() -> None:
    op.execute('CREATE SCHEMA "ayo"')
    op.create_table(
        "rides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("public_ride_id", sa.String(length=50), nullable=False),
        sa.Column("rider_name", sa.String(length=100), nullable=False),
        sa.Column("pickup", sa.String(length=200), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("ride_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("driver_id", sa.String(length=50), nullable=True),
        sa.Column("driver_name", sa.String(length=100), nullable=True),
        sa.Column("driver_distance_km", sa.Float(), nullable=True),
        sa.Column("driver_queue", postgresql.JSONB(), nullable=False),
        sa.Column("current_offer_index", sa.Integer(), nullable=True),
        sa.Column("current_offer", postgresql.JSONB(), nullable=True),
        sa.Column("gross_fare", sa.Float(), nullable=True),
        sa.Column("payment_method", sa.String(length=40), nullable=True),
        sa.Column("tip", sa.Float(), nullable=True),
        sa.Column("bonus", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="ck_rides_positive_version"),
        sa.PrimaryKeyConstraint("id", name="pk_rides"),
        sa.UniqueConstraint("public_ride_id", name="uq_rides_public_ride_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "legacy_wallets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("driver_id", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="ck_legacy_wallets_positive_version"),
        sa.PrimaryKeyConstraint("id", name="pk_legacy_wallets"),
        sa.UniqueConstraint("driver_id", name="uq_legacy_wallets_driver_id"),
        schema=SCHEMA,
        comment=(
            "Non-authoritative prototype state. Never treat as a financial ledger "
            "or migrate as trusted balances."
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrade is prohibited. Restore a verified backup or apply "
        "a reviewed forward-fix migration."
    )
