"""Add Customer Profile and Household Foundation.

Revision ID: 20260723_0048
Revises: 20260723_0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0048"
down_revision: str | Sequence[str] | None = "20260723_0047"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "customer_profiles",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("preferred_name", sa.String(120)),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("region", sa.String(63), nullable=False),
        sa.Column("timezone", sa.String(63), nullable=False),
        sa.Column("service_area_preference", sa.String(80)),
        sa.Column("profile_image_reference", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("profile_id", name="pk_customer_profiles"),
        sa.UniqueConstraint("subject_id", name="uq_customer_profiles_subject_id"),
        sa.CheckConstraint(
            "state IN ('active','suspended','closed')",
            name="ck_customer_profiles_valid_profile_state",
        ),
        sa.CheckConstraint(
            "version > 0", name="ck_customer_profiles_positive_profile_version"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "customer_household_relationships",
        sa.Column("relationship_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "inviting_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
            nullable=False,
        ),
        sa.Column(
            "invited_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(24), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint(
            "relationship_id", name="pk_customer_household_relationships"
        ),
        sa.UniqueConstraint(
            "inviting_subject_id",
            "invited_subject_id",
            name="uq_customer_household_direction",
        ),
        sa.CheckConstraint(
            "inviting_subject_id <> invited_subject_id",
            name="ck_customer_household_relationships_different_household_subjects",
        ),
        sa.CheckConstraint(
            "relationship_type IN ('family_member','trusted_friend','caregiver','other')",
            name="ck_customer_household_relationships_valid_household_type",
        ),
        sa.CheckConstraint(
            "state IN ('pending','active','suspended','removed')",
            name="ck_customer_household_relationships_valid_household_state",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_customer_household_relationships_positive_household_version",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_customer_household_invited_state",
        "customer_household_relationships",
        ["invited_subject_id", "state"],
        schema=SCHEMA,
    )
    op.create_table(
        "customer_emergency_contacts",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
            nullable=False,
        ),
        sa.Column(
            "contact_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("channel_reference", sa.String(200), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("contact_id", name="pk_customer_emergency_contacts"),
        sa.UniqueConstraint(
            "subject_id", "priority", name="uq_customer_emergency_priority"
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 20",
            name="ck_customer_emergency_contacts_valid_emergency_priority",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_customer_emergency_contacts_positive_emergency_version",
        ),
        schema=SCHEMA,
    )
    for table in (
        "customer_profiles",
        "customer_household_relationships",
        "customer_emergency_contacts",
    ):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE ON {SCHEMA}.{table} TO ayo_runtime")
        )


def downgrade() -> None:
    raise RuntimeError(
        "Forward-only migration: Customer Profile history must not be destructively removed"
    )
