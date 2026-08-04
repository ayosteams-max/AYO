"""Add immutable post-trip settlement, trust and receipt records.

Revision ID: 20260720_0031
Revises: 20260720_0030
Create Date: 2026-07-20
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0031"
down_revision: str | Sequence[str] | None = "20260720_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    jsonb = postgresql.JSONB()
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    created_at = datetime.now(UTC)
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000d001"),
                "code": "post_trip.read_own",
                "description": "Read an owned post-trip summary and receipt.",
                "created_at": created_at,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000d002"),
                "code": "post_trip.cash.confirm",
                "description": "Confirm own cash paid or received evidence.",
                "created_at": created_at,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000d003"),
                "code": "post_trip.rating.create",
                "description": "Submit one private rating for an owned completed trip.",
                "created_at": created_at,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000d004"),
                "code": "post_trip.internal.finalize",
                "description": "Finalize and settle an authoritative completed trip.",
                "created_at": created_at,
            },
        ],
    )
    op.create_table(
        "trip_evidence_packages",
        sa.Column("package_id", sa.UUID(), primary_key=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("package_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "post_trip_records",
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            primary_key=True,
        ),
        sa.Column(
            "package_id",
            sa.UUID(),
            sa.ForeignKey("ayo.trip_evidence_packages.package_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("cash_state", sa.String(32)),
        sa.Column("financial_breakdown", jsonb, nullable=False),
        sa.Column(
            "ledger_journal_id",
            sa.UUID(),
            sa.ForeignKey("ayo.ledger_journals.journal_id"),
        ),
        sa.Column(
            "wallet_entry_id",
            sa.UUID(),
            sa.ForeignKey("ayo.wallet_lineage_entries.wallet_entry_id"),
        ),
        sa.Column("rider_receipt_id", sa.UUID()),
        sa.Column("driver_receipt_id", sa.UUID()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version > 0", name="post_trip_positive_version"),
        schema="ayo",
    )
    op.create_table(
        "trip_cash_confirmations",
        sa.Column("confirmation_id", sa.UUID(), primary_key=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            nullable=False,
        ),
        sa.Column(
            "actor_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ride_id", "actor_role", name="uq_cash_confirmation_role"),
        sa.UniqueConstraint(
            "actor_identity_id",
            "idempotency_key_hash",
            name="uq_cash_confirmation_idempotency",
        ),
        sa.CheckConstraint(
            "actor_role IN ('rider','driver')", name="cash_confirmation_role"
        ),
        schema="ayo",
    )
    op.create_table(
        "trip_ratings",
        sa.Column("rating_id", sa.UUID(), primary_key=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            nullable=False,
        ),
        sa.Column(
            "author_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column(
            "target_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("feedback", sa.String(1000)),
        sa.Column("preference_requested", sa.Boolean(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "ride_id", "author_identity_id", name="uq_trip_rating_author"
        ),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="trip_rating_stars"),
        schema="ayo",
    )
    op.create_table(
        "preference_signals",
        sa.Column("preference_id", sa.UUID(), primary_key=True),
        sa.Column(
            "owner_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column(
            "target_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column(
            "source_ride_id", sa.UUID(), sa.ForeignKey("ayo.active_rides.ride_id")
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "owner_identity_id",
            "capability",
            "target_type",
            "target_identity_id",
            name="uq_preference_target",
        ),
        schema="ayo",
    )
    op.create_table(
        "trip_receipts",
        sa.Column("receipt_id", sa.UUID(), primary_key=True),
        sa.Column("receipt_number", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            nullable=False,
        ),
        sa.Column(
            "issued_to_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("receipt_type", sa.String(40), nullable=False),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("legal_entity", sa.String(160), nullable=False),
        sa.Column("regulatory_policy_version", sa.String(63), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ride_id", "receipt_type", name="uq_trip_receipt_type"),
        schema="ayo",
    )
    op.create_foreign_key(
        "fk_post_trip_rider_receipt",
        "post_trip_records",
        "trip_receipts",
        ["rider_receipt_id"],
        ["receipt_id"],
        source_schema="ayo",
        referent_schema="ayo",
    )
    op.create_table(
        "post_trip_outbox",
        sa.Column("message_id", sa.UUID(), primary_key=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column(
            "recipient_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("safe_payload", jsonb, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        schema="ayo",
    )
    op.create_foreign_key(
        "fk_post_trip_driver_receipt",
        "post_trip_records",
        "trip_receipts",
        ["driver_receipt_id"],
        ["receipt_id"],
        source_schema="ayo",
        referent_schema="ayo",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON ayo.post_trip_records TO ayo_runtime")
    for table in (
        "trip_evidence_packages",
        "trip_cash_confirmations",
        "trip_ratings",
        "preference_signals",
        "trip_receipts",
        "post_trip_outbox",
    ):
        op.execute(f"GRANT SELECT, INSERT ON ayo.{table} TO ayo_runtime")


def downgrade() -> None:
    op.drop_table("post_trip_outbox", schema="ayo")
    op.drop_constraint(
        "fk_post_trip_driver_receipt",
        "post_trip_records",
        schema="ayo",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_post_trip_rider_receipt",
        "post_trip_records",
        schema="ayo",
        type_="foreignkey",
    )
    for table in (
        "trip_receipts",
        "preference_signals",
        "trip_ratings",
        "trip_cash_confirmations",
        "post_trip_records",
        "trip_evidence_packages",
    ):
        op.drop_table(table, schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN "
        "('post_trip.read_own', 'post_trip.cash.confirm', "
        "'post_trip.rating.create', 'post_trip.internal.finalize')"
    )
