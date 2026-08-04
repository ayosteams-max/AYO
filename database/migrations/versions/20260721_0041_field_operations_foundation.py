"""Add Field Operations Platform foundation.

Revision ID: 20260721_0041
Revises: 20260721_0040
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0041"
down_revision: str | Sequence[str] | None = "20260721_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    now = datetime.now(UTC)
    codes = (
        (
            "00000000-0000-4000-8000-00000000f801",
            "field_operations.partner.manage",
            "Manage field partner profiles.",
        ),
        (
            "00000000-0000-4000-8000-00000000f802",
            "field_operations.configuration.manage",
            "Manage field roles and territories.",
        ),
        (
            "00000000-0000-4000-8000-00000000f803",
            "field_operations.assignment.manage",
            "Manage field assignments.",
        ),
        (
            "00000000-0000-4000-8000-00000000f804",
            "field_operations.case.manage",
            "Manage field assistance cases.",
        ),
        (
            "00000000-0000-4000-8000-00000000f805",
            "field_operations.activity.record",
            "Record field activity evidence.",
        ),
        (
            "00000000-0000-4000-8000-00000000f806",
            "field_operations.dashboard.read_own",
            "Read own field dashboard.",
        ),
        (
            "00000000-0000-4000-8000-00000000f807",
            "field_operations.partner.verify",
            "Verify minimum field partner status.",
        ),
    )
    op.bulk_insert(
        permissions,
        [
            {"permission_id": UUID(i), "code": c, "description": d, "created_at": now}
            for i, c, d in codes
        ],
    )
    op.create_table(
        "field_partners",
        sa.Column("partner_id", sa.UUID(), primary_key=True),
        sa.Column("public_partner_id", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "identity_id",
            sa.UUID(),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("photo_reference", sa.String(160), nullable=False),
        sa.Column("qr_reference_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("verification_status", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verification_status IN ('pending','verified','revoked')",
            name="field_partner_verification_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')", name="field_partner_status_valid"
        ),
        schema="ayo",
    )
    op.create_table(
        "field_partner_roles",
        sa.Column("role_id", sa.UUID(), primary_key=True),
        sa.Column("code", sa.String(63), nullable=False, unique=True),
        sa.Column("public_title", sa.String(100), nullable=False),
        sa.Column("allowed_activities", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "field_territories",
        sa.Column("territory_id", sa.UUID(), primary_key=True),
        sa.Column("market_code", sa.String(15), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("district", sa.String(100)),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "market_code",
            "region",
            "city",
            "district",
            "name",
            name="uq_field_territory_path",
        ),
        schema="ayo",
    )
    op.create_table(
        "field_partner_assignments",
        sa.Column("assignment_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partner_roles.role_id"),
            nullable=False,
        ),
        sa.Column(
            "territory_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_territories.territory_id"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="field_assignment_window_valid",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_field_assignment_partner_time",
        "field_partner_assignments",
        ["partner_id", "starts_at", "ends_at"],
        schema="ayo",
    )
    op.create_table(
        "field_assistance_cases",
        sa.Column("case_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column(
            "territory_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_territories.territory_id"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(63), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("capability_code", sa.String(63), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','completed','cancelled')",
            name="field_case_status_valid",
        ),
        schema="ayo",
    )
    op.create_table(
        "field_activities",
        sa.Column("activity_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column(
            "assignment_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partner_assignments.assignment_id"),
            nullable=False,
        ),
        sa.Column(
            "case_id", sa.UUID(), sa.ForeignKey("ayo.field_assistance_cases.case_id")
        ),
        sa.Column(
            "territory_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_territories.territory_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("subject_type", sa.String(63), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("quality_status", sa.String(63)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_index(
        "ix_field_activity_partner_time",
        "field_activities",
        ["partner_id", "occurred_at"],
        schema="ayo",
    )
    op.create_table(
        "field_operations_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "field_operations_idempotency",
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
            name="uq_field_operations_idempotency",
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON ayo.field_partners,ayo.field_partner_roles,ayo.field_territories,ayo.field_partner_assignments,ayo.field_assistance_cases TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT,INSERT ON ayo.field_activities,ayo.field_operations_events,ayo.field_operations_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_field_activity_partner_time", table_name="field_activities", schema="ayo"
    )
    for name in (
        "field_operations_idempotency",
        "field_operations_events",
        "field_activities",
        "field_assistance_cases",
    ):
        op.drop_table(name, schema="ayo")
    op.drop_index(
        "ix_field_assignment_partner_time",
        table_name="field_partner_assignments",
        schema="ayo",
    )
    for name in (
        "field_partner_assignments",
        "field_territories",
        "field_partner_roles",
        "field_partners",
    ):
        op.drop_table(name, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'field_operations.%'")
