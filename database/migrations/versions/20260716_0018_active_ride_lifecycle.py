"""Canonical post-assignment Active Ride lifecycle foundation.

Revision ID: 20260716_0018
Revises: 20260716_0017
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "20260716_0018"
down_revision: str | Sequence[str] | None = "20260716_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        item["name"] for item in inspector.get_columns("active_rides", schema="ayo")
    }
    additions = {
        "vehicle_id": sa.Column("vehicle_id", sa.Uuid()),
        "ride_request_id": sa.Column("ride_request_id", sa.Uuid()),
        "dispatch_handoff_id": sa.Column("dispatch_handoff_id", sa.Uuid()),
        "lifecycle_policy_version": sa.Column(
            "lifecycle_policy_version",
            sa.String(63),
            nullable=False,
            server_default=sa.text("'active_ride.v1'"),
        ),
        "source_assignment_version": sa.Column(
            "source_assignment_version", sa.Integer()
        ),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("active_rides", column, schema="ayo")
    indexes = {
        item["name"] for item in inspector.get_indexes("active_rides", schema="ayo")
    }
    if "uq_active_rides_immediate_assignment" not in indexes:
        op.create_index(
            "uq_active_rides_immediate_assignment",
            "active_rides",
            ["assignment_id"],
            unique=True,
            schema="ayo",
            postgresql_where=sa.text("dispatch_handoff_id IS NOT NULL"),
        )
    if "uq_active_rides_ride_request" not in indexes:
        op.create_index(
            "uq_active_rides_ride_request",
            "active_rides",
            ["ride_request_id"],
            unique=True,
            schema="ayo",
            postgresql_where=sa.text("ride_request_id IS NOT NULL"),
        )
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": "00000000-0000-4000-8000-000000000063",
                "code": "active_ride.internal.start",
                "description": "Create an Active Ride from an authoritative assignment.",
                "created_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code='active_ride.internal.start')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code='active_ride.internal.start'")
    op.drop_index(
        "uq_active_rides_ride_request", table_name="active_rides", schema="ayo"
    )
    op.drop_index(
        "uq_active_rides_immediate_assignment", table_name="active_rides", schema="ayo"
    )
    for column in (
        "source_assignment_version",
        "lifecycle_policy_version",
        "dispatch_handoff_id",
        "ride_request_id",
        "vehicle_id",
    ):
        op.drop_column("active_rides", column, schema="ayo")
