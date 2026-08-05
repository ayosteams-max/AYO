"""Courier Pickup deterministic idempotency replay V1.

Revision ID: 20260805_0057
Revises: 20260724_0056
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0057"
down_revision: str | Sequence[str] | None = "20260724_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "commerce_courier_pickup_idempotency"
    op.add_column(
        table,
        sa.Column(
            "digest_version", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        schema="ayo",
    )
    op.add_column(
        table,
        sa.Column(
            "response_schema_version",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        schema="ayo",
    )
    op.add_column(
        table,
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text())),
        schema="ayo",
    )
    op.create_check_constraint(
        "courier_pickup_idempotency_digest_version_valid",
        table,
        "digest_version BETWEEN 0 AND 32767",
        schema="ayo",
    )
    op.create_check_constraint(
        "courier_pickup_idempotency_response_schema_version_valid",
        table,
        "response_schema_version BETWEEN 0 AND 32767",
        schema="ayo",
    )
    op.create_check_constraint(
        "courier_pickup_idempotency_version_pair_valid",
        table,
        "(digest_version = 0 AND response_schema_version = 0 "
        "AND response_snapshot IS NULL) OR "
        "(digest_version = 1 AND response_schema_version = 1)",
        schema="ayo",
    )
    op.create_check_constraint(
        "courier_pickup_idempotency_completion_valid",
        table,
        "digest_version = 0 OR "
        "((response_version IS NULL AND response_snapshot IS NULL) OR "
        "(response_version IS NOT NULL AND response_snapshot IS NOT NULL))",
        schema="ayo",
    )


def downgrade() -> None:
    table = "commerce_courier_pickup_idempotency"
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM "
        "ayo.commerce_courier_pickup_idempotency "
        "WHERE digest_version = 1 AND response_version IS NOT NULL) "
        "THEN RAISE EXCEPTION "
        "'cannot downgrade: committed Courier Pickup V1 replay evidence exists'; "
        "END IF; END $$"
    )
    for constraint in (
        "courier_pickup_idempotency_completion_valid",
        "courier_pickup_idempotency_version_pair_valid",
        "courier_pickup_idempotency_response_schema_version_valid",
        "courier_pickup_idempotency_digest_version_valid",
    ):
        op.drop_constraint(constraint, table, schema="ayo", type_="check")
    op.drop_column(table, "response_snapshot", schema="ayo")
    op.drop_column(table, "response_schema_version", schema="ayo")
    op.drop_column(table, "digest_version", schema="ayo")
