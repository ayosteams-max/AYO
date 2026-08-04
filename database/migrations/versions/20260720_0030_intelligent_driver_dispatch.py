"""Add worker-role protection and explainable dispatch evidence.

Revision ID: 20260720_0030
Revises: 20260720_0029
Create Date: 2026-07-20
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0030"
down_revision: str | Sequence[str] | None = "20260720_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_capability_sessions",
        sa.Column("worker_session_id", sa.UUID(), primary_key=True),
        sa.Column(
            "identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column(
            "identity_session_id",
            sa.UUID(),
            sa.ForeignKey("ayo.sessions.session_id"),
            nullable=False,
        ),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("vehicle_id", sa.UUID()),
        sa.Column("service_zone_id", sa.UUID()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "capability IN ('ride_driver','food_courier','parcel_courier','home_service_provider')",
            name="worker_session_known_capability",
        ),
        sa.CheckConstraint(
            "state IN ('online','offline')", name="worker_session_known_state"
        ),
        sa.CheckConstraint("version > 0", name="worker_session_positive_version"),
        sa.CheckConstraint(
            "(state='online' AND stopped_at IS NULL) OR (state='offline' AND stopped_at IS NOT NULL)",
            name="worker_session_stop_consistency",
        ),
        schema="ayo",
    )
    op.create_index(
        "uq_worker_session_one_active_earning_role",
        "worker_capability_sessions",
        ["identity_id"],
        unique=True,
        schema="ayo",
        postgresql_where=sa.text("state='online'"),
    )
    op.create_index(
        "ix_worker_session_dispatch_lookup",
        "worker_capability_sessions",
        ["capability", "service_zone_id", "state"],
        schema="ayo",
    )
    inspector = sa.inspect(op.get_bind())
    candidate_columns = {
        column["name"]
        for column in inspector.get_columns(
            "immediate_dispatch_candidate_sets", schema="ayo"
        )
    }
    if "decision_evidence" not in candidate_columns:
        op.add_column(
            "immediate_dispatch_candidate_sets",
            sa.Column("decision_evidence", postgresql.JSONB(), nullable=True),
            schema="ayo",
        )
        op.execute(
            "UPDATE ayo.immediate_dispatch_candidate_sets SET decision_evidence='{}'::jsonb WHERE decision_evidence IS NULL"
        )
        op.alter_column(
            "immediate_dispatch_candidate_sets",
            "decision_evidence",
            nullable=False,
            schema="ayo",
        )
    offer_columns = {
        column["name"]
        for column in inspector.get_columns("immediate_dispatch_offers", schema="ayo")
    }
    if "route_evidence_id" not in offer_columns:
        op.add_column(
            "immediate_dispatch_offers",
            sa.Column("route_evidence_id", sa.String(128), nullable=True),
            schema="ayo",
        )
        op.add_column(
            "immediate_dispatch_offers",
            sa.Column("decision_reason_codes", postgresql.JSONB(), nullable=True),
            schema="ayo",
        )
        op.execute(
            "UPDATE ayo.immediate_dispatch_offers SET route_evidence_id='legacy.pre_ap095', decision_reason_codes='[\"legacy_migrated\"]'::jsonb WHERE route_evidence_id IS NULL"
        )
        op.alter_column(
            "immediate_dispatch_offers",
            "route_evidence_id",
            nullable=False,
            schema="ayo",
        )
        op.alter_column(
            "immediate_dispatch_offers",
            "decision_reason_codes",
            nullable=False,
            schema="ayo",
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
                "permission_id": UUID("00000000-0000-4000-8000-00000000c001"),
                "code": "dispatch.driver_mode.manage_own",
                "description": "Start and stop the authenticated driver's Ride Driver mode.",
                "created_at": datetime.now(UTC),
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000c002"),
                "code": "dispatch.canonical.offer.respond",
                "description": "Read and respond to the authenticated driver's canonical Immediate offer.",
                "created_at": datetime.now(UTC),
            },
        ],
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ayo.worker_capability_sessions TO ayo_runtime"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Dispatch decision evidence and worker-session history are forward-only; apply a corrective migration"
    )
