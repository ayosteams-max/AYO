"""Create reversible immediate-dispatch persistence and outbox.

Revision ID: 20260716_0008
Revises: 20260715_0007
Create Date: 2026-07-16
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0008"
down_revision: str | Sequence[str] | None = "20260715_0007"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB()
    op.create_table(
        "dispatch_ride_requests",
        sa.Column("ride_id", uuid, primary_key=True),
        sa.Column(
            "rider_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("pickup_place_id", sa.String(128), nullable=False),
        sa.Column("pickup_display_name", sa.String(200), nullable=False),
        sa.Column("destination_place_id", sa.String(128), nullable=False),
        sa.Column("destination_display_name", sa.String(200), nullable=False),
        sa.Column("service_type", sa.String(40), nullable=False),
        sa.Column("quote_id", uuid, nullable=False),
        sa.Column("fare_amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("pricing_version", sa.String(63), nullable=False),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "assigned_driver_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
        ),
        sa.Column("active_offer_id", uuid),
        sa.Column(
            "attempted_driver_ids",
            jsonb,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("search_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "fare_amount_minor >= 0",
            name="ck_dispatch_ride_requests_dispatch_ride_nonnegative_fare",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_dispatch_ride_requests_dispatch_ride_valid_currency",
        ),
        sa.CheckConstraint(
            "service_type ~ '^[a-z][a-z0-9_.-]{1,39}$'",
            name="ck_dispatch_ride_requests_dispatch_ride_valid_service_type",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_dispatch_ride_requests_dispatch_ride_positive_version",
        ),
        sa.CheckConstraint(
            "pickup_place_id <> destination_place_id",
            name="ck_dispatch_ride_requests_dispatch_ride_distinct_places",
        ),
        sa.CheckConstraint(
            "state IN ('searching','offering','assigned','no_driver_available','rider_cancelled')",
            name="ck_dispatch_ride_requests_dispatch_ride_valid_state",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dispatch_rides_rider_state",
        "dispatch_ride_requests",
        ["rider_identity_id", "state"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dispatch_rides_search_expiry",
        "dispatch_ride_requests",
        ["search_expires_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("state IN ('searching','offering')"),
    )
    op.create_index(
        "uq_dispatch_active_ride_per_rider",
        "dispatch_ride_requests",
        ["rider_identity_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("state IN ('searching','offering','assigned')"),
    )

    op.create_table(
        "dispatch_attempts",
        sa.Column("attempt_id", uuid, primary_key=True),
        sa.Column(
            "ride_id",
            uuid,
            sa.ForeignKey("ayo.dispatch_ride_requests.ride_id"),
            nullable=False,
        ),
        sa.Column(
            "driver_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("pickup_eta_seconds", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(63), nullable=False),
        sa.Column("reason_codes", jsonb, nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_dispatch_attempts_dispatch_attempt_positive_sequence",
        ),
        sa.CheckConstraint(
            "pickup_eta_seconds BETWEEN 0 AND 14400",
            name="ck_dispatch_attempts_dispatch_attempt_valid_eta",
        ),
        sa.CheckConstraint(
            "outcome IN ('offered','accepted','declined','expired','revoked')",
            name="ck_dispatch_attempts_dispatch_attempt_valid_outcome",
        ),
        sa.UniqueConstraint(
            "ride_id", "sequence_number", name="uq_dispatch_attempts_ride_id"
        ),
        sa.UniqueConstraint(
            "ride_id",
            "driver_identity_id",
            name="uq_dispatch_attempts_ride_id_driver_identity_id",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "dispatch_driver_offers",
        sa.Column("offer_id", uuid, primary_key=True),
        sa.Column(
            "attempt_id",
            uuid,
            sa.ForeignKey("ayo.dispatch_attempts.attempt_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "ride_id",
            uuid,
            sa.ForeignKey("ayo.dispatch_ride_requests.ride_id"),
            nullable=False,
        ),
        sa.Column(
            "driver_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("policy_version", sa.String(63), nullable=False),
        sa.Column("score_snapshot", jsonb, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_dispatch_driver_offers_dispatch_offer_valid_lifetime",
        ),
        sa.CheckConstraint(
            "state IN ('created','accepted','declined','expired','revoked')",
            name="ck_dispatch_driver_offers_dispatch_offer_valid_state",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dispatch_offers_expiry",
        "dispatch_driver_offers",
        ["expires_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("state = 'created'"),
    )
    op.create_index(
        "uq_dispatch_active_offer_per_ride",
        "dispatch_driver_offers",
        ["ride_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("state = 'created'"),
    )
    op.create_index(
        "uq_dispatch_active_offer_per_driver",
        "dispatch_driver_offers",
        ["driver_identity_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("state = 'created'"),
    )
    op.create_table(
        "dispatch_assignments",
        sa.Column("assignment_id", uuid, primary_key=True),
        sa.Column(
            "ride_id",
            uuid,
            sa.ForeignKey("ayo.dispatch_ride_requests.ride_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "offer_id",
            uuid,
            sa.ForeignKey("ayo.dispatch_driver_offers.offer_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "driver_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= assigned_at",
            name="ck_dispatch_assignments_dispatch_assignment_valid_lifetime",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_dispatch_active_assignment_per_driver",
        "dispatch_assignments",
        ["driver_identity_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_table(
        "dispatch_idempotency_records",
        sa.Column(
            "rider_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
            primary_key=True,
        ),
        sa.Column("key_fingerprint", sa.String(64), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "ride_id",
            uuid,
            sa.ForeignKey("ayo.dispatch_ride_requests.ride_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_dispatch_idempotency_records_dispatch_idempotency_valid_lifetime",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "dispatch_outbox",
        sa.Column("message_id", uuid, primary_key=True),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", uuid, nullable=False),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(64)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(63)),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_dispatch_outbox_dispatch_outbox_nonnegative_attempts",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dispatch_outbox_pending",
        "dispatch_outbox",
        ["available_at", "occurred_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NULL"),
    )

    permissions = sa.table(
        "permissions",
        sa.column("permission_id", uuid),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": "00000000-0000-4000-8000-000000000030",
                "code": "dispatch.rider.request",
                "description": "Create and recover the authenticated rider's rides.",
                "created_at": datetime.now(UTC),
            },
            {
                "permission_id": "00000000-0000-4000-8000-000000000031",
                "code": "dispatch.driver.offer.respond",
                "description": "Read and respond to the authenticated driver's offers.",
                "created_at": datetime.now(UTC),
            },
            {
                "permission_id": "00000000-0000-4000-8000-000000000032",
                "code": "dispatch.worker.recover",
                "description": "Run bounded server-side dispatch recovery.",
                "created_at": datetime.now(UTC),
            },
        ],
    )
    op.execute(
        "REVOKE ALL ON TABLE ayo.dispatch_ride_requests, ayo.dispatch_attempts, ayo.dispatch_driver_offers, ayo.dispatch_assignments, ayo.dispatch_idempotency_records, ayo.dispatch_outbox FROM PUBLIC"
    )
    op.execute("""DO $ayo$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
      GRANT SELECT, INSERT, UPDATE ON ayo.dispatch_ride_requests, ayo.dispatch_attempts, ayo.dispatch_driver_offers, ayo.dispatch_outbox TO ayo_runtime;
      GRANT SELECT, INSERT ON ayo.dispatch_assignments, ayo.dispatch_idempotency_records TO ayo_runtime;
      REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ayo.dispatch_ride_requests, ayo.dispatch_attempts, ayo.dispatch_driver_offers, ayo.dispatch_assignments, ayo.dispatch_idempotency_records, ayo.dispatch_outbox FROM ayo_runtime;
      REVOKE UPDATE ON ayo.dispatch_assignments, ayo.dispatch_idempotency_records FROM ayo_runtime;
    END IF; END $ayo$""")


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM ayo.permissions WHERE code IN "
        "('dispatch.rider.request','dispatch.driver.offer.respond',"
        "'dispatch.worker.recover'))"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('dispatch.rider.request','dispatch.driver.offer.respond','dispatch.worker.recover')"
    )
    op.drop_index(
        "ix_dispatch_outbox_pending", table_name="dispatch_outbox", schema=SCHEMA
    )
    op.drop_table("dispatch_outbox", schema=SCHEMA)
    op.drop_table("dispatch_idempotency_records", schema=SCHEMA)
    op.drop_index(
        "uq_dispatch_active_assignment_per_driver",
        table_name="dispatch_assignments",
        schema=SCHEMA,
    )
    op.drop_table("dispatch_assignments", schema=SCHEMA)
    op.drop_index(
        "uq_dispatch_active_offer_per_driver",
        table_name="dispatch_driver_offers",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_dispatch_active_offer_per_ride",
        table_name="dispatch_driver_offers",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_dispatch_offers_expiry", table_name="dispatch_driver_offers", schema=SCHEMA
    )
    op.drop_table("dispatch_driver_offers", schema=SCHEMA)
    op.drop_table("dispatch_attempts", schema=SCHEMA)
    op.drop_index(
        "uq_dispatch_active_ride_per_rider",
        table_name="dispatch_ride_requests",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_dispatch_rides_search_expiry",
        table_name="dispatch_ride_requests",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_dispatch_rides_rider_state",
        table_name="dispatch_ride_requests",
        schema=SCHEMA,
    )
    op.drop_table("dispatch_ride_requests", schema=SCHEMA)
