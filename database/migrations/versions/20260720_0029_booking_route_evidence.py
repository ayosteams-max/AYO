"""Add immutable booking route evidence and confirmation linkage.

Revision ID: 20260720_0029
Revises: 20260720_0028
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0029"
down_revision: str | Sequence[str] | None = "20260720_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_route_evidence",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column("booking_session_hash", sa.String(64), nullable=False),
        sa.Column(
            "rider_identity_id", sa.UUID(), sa.ForeignKey("ayo.identities.identity_id")
        ),
        sa.Column("pickup_payload", postgresql.JSONB(), nullable=False),
        sa.Column("destination_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "service_zone_id",
            sa.UUID(),
            sa.ForeignKey("ayo.service_zones.zone_id"),
            nullable=False,
        ),
        sa.Column("service_zone_version", sa.String(63), nullable=False),
        sa.Column("service_type", sa.String(32), nullable=False),
        sa.Column("route_payload", postgresql.JSONB(), nullable=False),
        sa.Column("quote_payload", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "service_type='immediate_standard'", name="booking_route_immediate_standard"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="booking_route_positive_expiry"
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_booking_route_session_expiry",
        "booking_route_evidence",
        ["booking_session_hash", "expires_at"],
        schema="ayo",
    )
    op.create_table(
        "booking_confirmations",
        sa.Column("confirmation_id", sa.UUID(), primary_key=True),
        sa.Column(
            "evidence_id",
            sa.UUID(),
            sa.ForeignKey("ayo.booking_route_evidence.evidence_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column(
            "ride_request_id",
            sa.UUID(),
            sa.ForeignKey("ayo.canonical_ride_requests.request_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "rider_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "rider_identity_id",
            "idempotency_key_hash",
            name="uq_booking_confirmation_rider_key",
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.booking_route_evidence, ayo.booking_confirmations TO ayo_runtime"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Immutable booking evidence is forward-only; apply a corrective migration"
    )
