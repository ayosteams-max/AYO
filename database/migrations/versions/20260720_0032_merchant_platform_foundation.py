"""Add reusable Merchant Platform foundation.

Revision ID: 20260720_0032
Revises: 20260720_0031
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0032"
down_revision: str | Sequence[str] | None = "20260720_0031"
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
    now = datetime.now(UTC)
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID(f"00000000-0000-4000-8000-00000000e00{i}"),
                "code": code,
                "description": description,
                "created_at": now,
            }
            for i, (code, description) in enumerate(
                (
                    ("merchant.register_own", "Create an owned merchant profile."),
                    ("merchant.manage_own", "Manage an owned merchant profile."),
                    (
                        "merchant.dashboard.read_own",
                        "Read an owned merchant dashboard.",
                    ),
                    (
                        "merchant.assist",
                        "Assist onboarding without credential ownership.",
                    ),
                    (
                        "merchant.verification.review",
                        "Review merchant verification evidence.",
                    ),
                    (
                        "merchant.catalogue.review",
                        "Review merchant catalogue readiness.",
                    ),
                    (
                        "merchant.program.manage",
                        "Configure merchant partner programmes.",
                    ),
                ),
                1,
            )
        ],
    )
    op.create_table(
        "merchant_profiles",
        sa.Column("merchant_id", sa.UUID(), primary_key=True),
        sa.Column(
            "owner_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("legal_name", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("onboarding_source", sa.String(24), nullable=False),
        sa.Column(
            "assisted_by_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("capability_code", sa.String(63), nullable=False),
        sa.Column("market_code", sa.String(15), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "owner_identity_id <> assisted_by_identity_id",
            name="merchant_owner_not_representative",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_merchant_owner",
        "merchant_profiles",
        ["owner_identity_id", "created_at"],
        schema="ayo",
    )
    op.create_table(
        "merchant_branches",
        sa.Column("branch_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("address_label", sa.String(240), nullable=False),
        sa.Column("timezone", sa.String(63), nullable=False),
        sa.Column("operating_hours", jsonb, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("merchant_id", "name", name="uq_merchant_branch_name"),
        schema="ayo",
    )
    op.create_table(
        "merchant_verifications",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("opaque_reference", sa.String(160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "reviewed_by_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
        ),
        sa.Column("reason_code", sa.String(63)),
        sa.UniqueConstraint(
            "merchant_id", "kind", name="uq_merchant_verification_kind"
        ),
        schema="ayo",
    )
    op.create_table(
        "merchant_partner_programs",
        sa.Column("program_id", sa.UUID(), primary_key=True),
        sa.Column("code", sa.String(63), nullable=False, unique=True),
        sa.Column("badge_label", sa.String(80), nullable=False),
        sa.Column("capability_code", sa.String(63), nullable=False),
        sa.Column("market_code", sa.String(15), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("participant_limit", sa.Integer()),
        sa.Column("benefit_configuration", jsonb, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("closes_at > opens_at", name="merchant_program_window"),
        sa.CheckConstraint(
            "participant_limit IS NULL OR participant_limit > 0",
            name="merchant_program_limit",
        ),
        schema="ayo",
    )
    op.create_table(
        "merchant_program_enrollments",
        sa.Column("enrollment_id", sa.UUID(), primary_key=True),
        sa.Column(
            "program_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_partner_programs.program_id"),
            nullable=False,
        ),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "program_id", "merchant_id", name="uq_merchant_program_enrollment"
        ),
        schema="ayo",
    )
    op.create_table(
        "merchant_catalogue_items",
        sa.Column("item_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column(
            "branch_id", sa.UUID(), sa.ForeignKey("ayo.merchant_branches.branch_id")
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("category_code", sa.String(63), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_merchant_catalogue_page",
        "merchant_catalogue_items",
        ["merchant_id", "created_at", "item_id"],
        schema="ayo",
    )
    op.create_table(
        "merchant_assistance",
        sa.Column("assistance_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column(
            "representative_identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("activity_code", sa.String(63), nullable=False),
        sa.Column("verified_onboarding", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "merchant_id",
            "representative_identity_id",
            "activity_code",
            name="uq_merchant_assistance_activity",
        ),
        schema="ayo",
    )
    op.create_table(
        "merchant_idempotency",
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.String(63), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_reference", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_identity_id",
            "operation",
            "idempotency_key",
            name="uq_merchant_idempotency",
        ),
        schema="ayo",
    )
    op.create_table(
        "merchant_outbox",
        sa.Column("message_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column("safe_payload", jsonb, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ayo.merchant_profiles, ayo.merchant_verifications, ayo.merchant_catalogue_items TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.merchant_branches, ayo.merchant_partner_programs, ayo.merchant_program_enrollments, ayo.merchant_assistance, ayo.merchant_idempotency, ayo.merchant_outbox TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "merchant_outbox",
        "merchant_idempotency",
        "merchant_assistance",
        "merchant_catalogue_items",
        "merchant_program_enrollments",
        "merchant_partner_programs",
        "merchant_verifications",
        "merchant_branches",
        "merchant_profiles",
    ):
        op.drop_table(table, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'merchant.%'")
