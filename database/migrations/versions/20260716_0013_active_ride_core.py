"""Add Mission 19 active ride authority and advisory persistence.

Revision ID: 20260716_0013
Revises: 20260716_0012
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260716_0013"
down_revision: str | Sequence[str] | None = "20260716_0012"
branch_labels = None
depends_on = None

TABLES = (
    "active_rides",
    "active_ride_events",
    "active_ride_idempotency_records",
    "active_ride_projection_checkpoints",
    "active_ride_pickup_verifications",
    "active_ride_evidence",
    "active_ride_confidence_decisions",
    "active_ride_pickup_recommendations",
    "active_ride_recovery_checkpoints",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)
    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
        GRANT SELECT, INSERT ON ayo.active_rides, ayo.active_ride_events,
          ayo.active_ride_idempotency_records, ayo.active_ride_projection_checkpoints,
          ayo.active_ride_pickup_verifications, ayo.active_ride_evidence,
          ayo.active_ride_confidence_decisions, ayo.active_ride_pickup_recommendations,
          ayo.active_ride_recovery_checkpoints TO ayo_runtime;
        GRANT UPDATE ON ayo.active_rides, ayo.active_ride_projection_checkpoints,
          ayo.active_ride_pickup_verifications, ayo.active_ride_pickup_recommendations,
          ayo.active_ride_recovery_checkpoints TO ayo_runtime;
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
            "41",
            "active_ride.read",
            "Read an owned active ride projection and event stream.",
        ),
        (
            "42",
            "active_ride.rider.command",
            "Submit an authenticated rider active-ride command.",
        ),
        (
            "43",
            "active_ride.driver.command",
            "Submit an assigned driver active-ride command.",
        ),
        ("44", "active_ride.worker.run", "Run bounded active-ride recovery workers."),
        ("45", "active_ride.worker.health.read", "Read active-ride worker health."),
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
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'active_ride.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'active_ride.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
