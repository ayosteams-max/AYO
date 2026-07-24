"""Add Field Assistance lifecycle and independent quality review.

Revision ID: 20260721_0042
Revises: 20260721_0041
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0042"
down_revision: str | Sequence[str] | None = "20260721_0041"
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
            "00000000-0000-4000-8000-00000000f811",
            "field_operations.case.confirm_owner",
            "Confirm assistance as the authenticated owner.",
        ),
        (
            "00000000-0000-4000-8000-00000000f812",
            "field_operations.case.review",
            "Independently review submitted assistance cases.",
        ),
        (
            "00000000-0000-4000-8000-00000000f813",
            "field_operations.quality.record",
            "Record immutable partner conduct evidence.",
        ),
        (
            "00000000-0000-4000-8000-00000000f814",
            "field_operations.quality.read",
            "Read bounded Field Operations quality metrics.",
        ),
    )
    op.bulk_insert(
        permissions,
        [
            {"permission_id": UUID(i), "code": c, "description": d, "created_at": now}
            for i, c, d in codes
        ],
    )

    op.drop_constraint(
        "field_case_status_valid", "field_assistance_cases", schema="ayo", type_="check"
    )
    op.alter_column(
        "field_assistance_cases",
        "status",
        type_=sa.String(40),
        existing_type=sa.String(20),
        schema="ayo",
    )
    op.add_column(
        "field_assistance_cases",
        sa.Column("owner_identity_id", sa.UUID()),
        schema="ayo",
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'assigned' WHERE status = 'pending'"
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'business_owner_assisted' WHERE status = 'completed'"
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'rejected' WHERE status = 'cancelled'"
    )
    op.create_check_constraint(
        "field_case_status_valid",
        "field_assistance_cases",
        "status IN ('assigned','in_progress','business_owner_assisted','owner_verification_completed','submitted_for_review','approved','returned_for_correction','rejected')",
        schema="ayo",
    )
    op.create_unique_constraint(
        "uq_field_case_subject_capability",
        "field_assistance_cases",
        ["subject_type", "subject_id", "capability_code"],
        schema="ayo",
    )
    op.create_index(
        "ix_field_case_status_territory",
        "field_assistance_cases",
        ["status", "territory_id", "case_id"],
        schema="ayo",
    )
    op.create_table(
        "field_case_evidence",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "case_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_assistance_cases.case_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("from_status", sa.String(40)),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("actor_role", sa.String(40), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("reason_code", sa.String(63)),
        sa.Column("checklist", sa.JSON()),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "case_id", "case_version", name="uq_field_case_evidence_version"
        ),
        schema="ayo",
    )
    op.create_table(
        "field_partner_conduct_evidence",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("recorded_by_identity_id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.execute(
        "INSERT INTO ayo.field_case_evidence (evidence_id,case_id,event_type,from_status,to_status,actor_identity_id,actor_role,evidence_reference,case_version,occurred_at) SELECT gen_random_uuid(),c.case_id,'field.case.migrated',NULL,c.status,p.identity_id,'system','phase2-migrated-case-' || c.case_id::text,c.version,c.updated_at FROM ayo.field_assistance_cases c JOIN ayo.field_partners p ON p.partner_id = c.partner_id"
    )
    op.execute("GRANT SELECT,UPDATE ON ayo.field_assistance_cases TO ayo_runtime")
    op.execute(
        "GRANT SELECT,INSERT ON ayo.field_case_evidence,ayo.field_partner_conduct_evidence TO ayo_runtime"
    )


def downgrade() -> None:
    op.drop_table("field_partner_conduct_evidence", schema="ayo")
    op.drop_table("field_case_evidence", schema="ayo")
    op.drop_index(
        "ix_field_case_status_territory",
        table_name="field_assistance_cases",
        schema="ayo",
    )
    op.drop_constraint(
        "uq_field_case_subject_capability",
        "field_assistance_cases",
        schema="ayo",
        type_="unique",
    )
    op.drop_constraint(
        "field_case_status_valid", "field_assistance_cases", schema="ayo", type_="check"
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'pending' WHERE status IN ('assigned','returned_for_correction')"
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'in_progress' WHERE status IN ('business_owner_assisted','owner_verification_completed','submitted_for_review')"
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'completed' WHERE status = 'approved'"
    )
    op.execute(
        "UPDATE ayo.field_assistance_cases SET status = 'cancelled' WHERE status = 'rejected'"
    )
    op.alter_column(
        "field_assistance_cases",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(40),
        schema="ayo",
    )
    op.create_check_constraint(
        "field_case_status_valid",
        "field_assistance_cases",
        "status IN ('pending','in_progress','completed','cancelled')",
        schema="ayo",
    )
    op.drop_column("field_assistance_cases", "owner_identity_id", schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('field_operations.case.confirm_owner','field_operations.case.review','field_operations.quality.record','field_operations.quality.read')"
    )
