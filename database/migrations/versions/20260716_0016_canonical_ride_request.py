"""Canonical Immediate Standard ride request and pickup foundation.

Revision ID: 20260716_0016
Revises: 20260716_0015
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260716_0016"
down_revision: str | Sequence[str] | None = "20260716_0015"
branch_labels = None
depends_on = None

TABLES = (
    "service_zones",
    "canonical_pickups",
    "canonical_destinations",
    "canonical_ride_requests",
    "ride_request_validation_decisions",
    "ride_request_idempotency",
    "ride_request_events",
    "ride_request_outbox",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        table = metadata.tables[f"ayo.{name}"]
        future_constraints = [
            constraint
            for constraint in table.foreign_key_constraints
            if constraint.referred_table.fullname == "ayo.canonical_subjects"
        ]
        for constraint in future_constraints:
            table.constraints.remove(constraint)
        try:
            table.create(bind)
        finally:
            for constraint in future_constraints:
                table.append_constraint(constraint)
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
            "55",
            "ride_request.create",
            "Create an authenticated rider's Immediate Standard request.",
        ),
        (
            "56",
            "ride_request.read_own",
            "Read the authenticated rider's canonical request.",
        ),
        (
            "57",
            "ride_request.cancel_own",
            "Cancel the authenticated rider's pre-dispatch request.",
        ),
        (
            "58",
            "ride_request.support.read",
            "Read an explicitly authorized support projection.",
        ),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-0000000000{s}",
                "code": c,
                "description": d,
                "created_at": datetime.now(UTC),
            }
            for s, c, d in values
        ],
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
    GRANT SELECT, INSERT ON ayo.canonical_pickups, ayo.canonical_destinations,
      ayo.canonical_ride_requests, ayo.ride_request_validation_decisions,
      ayo.ride_request_idempotency, ayo.ride_request_events, ayo.ride_request_outbox TO ayo_runtime;
    GRANT SELECT ON ayo.service_zones TO ayo_runtime;
    GRANT UPDATE ON ayo.canonical_ride_requests, ayo.ride_request_outbox TO ayo_runtime;
    END IF; END $$""")


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'ride_request.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'ride_request.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
