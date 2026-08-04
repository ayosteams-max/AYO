"""Add canonical subject/account compatibility foundation.

Revision ID: 20260723_0045
Revises: 20260723_0044
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0045"
down_revision: str | Sequence[str] | None = "20260723_0044"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "canonical_subjects",
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_kind", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "subject_kind IN ('human','service','other')",
            name="ck_canonical_subjects_valid_subject_kind",
        ),
        sa.CheckConstraint(
            "version > 0", name="ck_canonical_subjects_positive_version"
        ),
        sa.PrimaryKeyConstraint("subject_id", name="pk_canonical_subjects"),
        schema=SCHEMA,
    )
    op.create_table(
        "identity_accounts",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending_activation','active','locked','suspended','closed')",
            name="ck_identity_accounts_valid_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_identity_accounts_positive_version"),
        sa.PrimaryKeyConstraint("account_id", name="pk_identity_accounts"),
        sa.UniqueConstraint("subject_id", name="uq_identity_accounts_subject_id"),
        sa.UniqueConstraint(
            "account_id",
            "subject_id",
            name="uq_identity_accounts_account_id",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_identity_accounts_state",
        "identity_accounts",
        ["state"],
        schema=SCHEMA,
    )
    op.create_table(
        "legacy_identity_mappings",
        sa.Column("mapping_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "legacy_identity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.canonical_subjects.subject_id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
        ),
        sa.Column("semantic", sa.String(40), nullable=False),
        sa.Column("mapping_state", sa.String(24), nullable=False),
        sa.Column("provenance", sa.String(63), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "semantic IN ('canonical_subject','account','business_participant',"
            "'authentication_actor','authorization_principal','resource_owner',"
            "'audit_actor','ambiguous_legacy_reference')",
            name="ck_legacy_identity_mappings_valid_semantic",
        ),
        sa.CheckConstraint(
            "mapping_state IN ('subject_mapped','account_mapped','ambiguous')",
            name="ck_legacy_identity_mappings_valid_mapping_state",
        ),
        sa.CheckConstraint(
            "(mapping_state = 'account_mapped' AND account_id IS NOT NULL) OR "
            "(mapping_state <> 'account_mapped' AND account_id IS NULL)",
            name="ck_legacy_identity_mappings_account_mapping_consistent",
        ),
        sa.CheckConstraint(
            "version > 0", name="ck_legacy_identity_mappings_positive_version"
        ),
        sa.PrimaryKeyConstraint("mapping_id", name="pk_legacy_identity_mappings"),
        sa.ForeignKeyConstraint(
            ["account_id", "subject_id"],
            ["ayo.identity_accounts.account_id", "ayo.identity_accounts.subject_id"],
            name="fk_legacy_identity_mappings_account_id_identity_accounts",
        ),
        sa.UniqueConstraint(
            "legacy_identity_id",
            name="uq_legacy_identity_mappings_legacy_identity_id",
        ),
        sa.UniqueConstraint(
            "subject_id", name="uq_legacy_identity_mappings_subject_id"
        ),
        sa.UniqueConstraint(
            "account_id", name="uq_legacy_identity_mappings_account_id"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_legacy_identity_mappings_state",
        "legacy_identity_mappings",
        ["mapping_state", "semantic"],
        schema=SCHEMA,
    )
    op.execute("REVOKE ALL ON ayo.canonical_subjects FROM PUBLIC")
    op.execute("REVOKE ALL ON ayo.identity_accounts FROM PUBLIC")
    op.execute("REVOKE ALL ON ayo.legacy_identity_mappings FROM PUBLIC")
    op.execute(
        """
        DO $ayo$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
                GRANT SELECT, INSERT ON ayo.canonical_subjects TO ayo_runtime;
                REVOKE UPDATE, DELETE, TRUNCATE ON ayo.canonical_subjects
                    FROM ayo_runtime;
                GRANT SELECT, INSERT, UPDATE ON ayo.identity_accounts TO ayo_runtime;
                REVOKE DELETE, TRUNCATE ON ayo.identity_accounts FROM ayo_runtime;
                GRANT SELECT, INSERT, UPDATE ON ayo.legacy_identity_mappings
                    TO ayo_runtime;
                REVOKE DELETE, TRUNCATE ON ayo.legacy_identity_mappings
                    FROM ayo_runtime;
            END IF;
        END
        $ayo$
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive canonical identity compatibility downgrade is prohibited. "
        "Apply a reviewed forward fix or restore a verified backup."
    )
