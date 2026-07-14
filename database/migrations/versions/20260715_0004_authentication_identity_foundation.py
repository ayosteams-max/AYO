"""Create the authentication and identity foundation.

Revision ID: 20260715_0004
Revises: 20260715_0003
Create Date: 2026-07-15

This revision is immutable after application to any shared environment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0004"
down_revision: str | Sequence[str] | None = "20260715_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_identities_positive_version"),
        sa.CheckConstraint(
            "identity_type IN ('anonymous','rider','driver','staff','administrator',"
            "'service','merchant','service_provider')",
            name="ck_identities_valid_identity_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','active','suspended','locked','disabled',"
            "'recovery_pending','deletion_pending')",
            name="ck_identities_valid_status",
        ),
        sa.PrimaryKeyConstraint("identity_id", name="pk_identities"),
        sa.UniqueConstraint("public_id", name="uq_identities_public_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_identities_type_status",
        "identities",
        ["identity_type", "status"],
        schema=SCHEMA,
    )
    op.create_table(
        "identity_authentication_methods",
        sa.Column("method_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("lookup_reference", sa.LargeBinary(32), nullable=True),
        sa.Column("assurance_level", sa.String(32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "method_type IN ('phone_otp','email_verification','password','passkey',"
            "'recovery_code','staff_mfa','service_credential')",
            name="ck_identity_authentication_methods_valid_method_type",
        ),
        sa.CheckConstraint(
            "assurance_level IN ('basic','multi_factor','phishing_resistant')",
            name="ck_identity_authentication_methods_valid_assurance_level",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["ayo.identities.identity_id"],
            name="fk_identity_authentication_methods_identity_id_identities",
        ),
        sa.PrimaryKeyConstraint("method_id", name="pk_identity_authentication_methods"),
        sa.UniqueConstraint(
            "identity_id",
            "method_type",
            "lookup_reference",
            name="uq_identity_authentication_methods_identity_id",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_identity_auth_methods_identity",
        "identity_authentication_methods",
        ["identity_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "credential_verifiers",
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme", sa.String(32), nullable=False),
        sa.Column("verifier", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["method_id"],
            ["ayo.identity_authentication_methods.method_id"],
            name="fk_credential_verifiers_method_id_identity_authentication_methods",
        ),
        sa.PrimaryKeyConstraint("credential_id", name="pk_credential_verifiers"),
        sa.UniqueConstraint("method_id", name="uq_credential_verifiers_method_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "authentication_challenges",
        sa.Column("challenge_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("verifier", sa.LargeBinary(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_authentication_challenges_nonnegative_attempts",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_authentication_challenges_bounded_max_attempts",
        ),
        sa.CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_authentication_challenges_attempts_within_limit",
        ),
        sa.PrimaryKeyConstraint("challenge_id", name="pk_authentication_challenges"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_auth_challenges_expires_at",
        "authentication_challenges",
        ["expires_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "identity_devices",
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint_reference", sa.LargeBinary(32), nullable=False),
        sa.Column("device_category", sa.String(32), nullable=False),
        sa.Column("operating_system_family", sa.String(32), nullable=False),
        sa.Column("trust_state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "trust_state IN ('unknown','recognized','trusted','restricted')",
            name="ck_identity_devices_valid_trust_state",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["ayo.identities.identity_id"],
            name="fk_identity_devices_identity_id_identities",
        ),
        sa.PrimaryKeyConstraint("device_id", name="pk_identity_devices"),
        sa.UniqueConstraint(
            "identity_id",
            "fingerprint_reference",
            name="uq_identity_devices_identity_id",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_identity_devices_identity",
        "identity_devices",
        ["identity_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "token_families",
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "rotation_counter",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "rotation_counter >= 0",
            name="ck_token_families_nonnegative_rotation_counter",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked','expired')",
            name="ck_token_families_valid_status",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_token_families_valid_lifetime"
        ),
        sa.PrimaryKeyConstraint("family_id", name="pk_token_families"),
        sa.UniqueConstraint(
            "current_token_hash", name="uq_token_families_current_token_hash"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_token_families_identity_status",
        "token_families",
        ["identity_id", "status"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_token_families_session", "token_families", ["session_id"], schema=SCHEMA
    )
    op.create_table(
        "refresh_token_rotations",
        sa.Column("rotation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("rotation_counter", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["ayo.token_families.family_id"],
            name="fk_refresh_token_rotations_family_id_token_families",
        ),
        sa.PrimaryKeyConstraint("rotation_id", name="pk_refresh_token_rotations"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_rotations_token_hash"),
        sa.UniqueConstraint(
            "family_id", "rotation_counter", name="uq_refresh_token_rotations_family_id"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "recovery_cases",
        sa.Column("recovery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("recovery_id", name="pk_recovery_cases"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_recovery_cases_identity_status",
        "recovery_cases",
        ["identity_id", "status"],
        schema=SCHEMA,
    )

    for column, type_ in (
        ("identity_id", postgresql.UUID(as_uuid=True)),
        ("device_id", postgresql.UUID(as_uuid=True)),
        ("device_fingerprint_ref", sa.LargeBinary(32)),
        ("device_category", sa.String(32)),
        ("application_version", sa.String(32)),
        ("operating_system_family", sa.String(32)),
        ("authentication_method", sa.String(32)),
        ("assurance_level", sa.String(32)),
        ("risk_state", sa.String(32)),
        ("ip_risk_ref", sa.LargeBinary(32)),
        ("token_family_id", postgresql.UUID(as_uuid=True)),
    ):
        op.add_column(
            "sessions", sa.Column(column, type_, nullable=True), schema=SCHEMA
        )
    op.add_column(
        "sessions",
        sa.Column(
            "refresh_rotation_counter",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_sessions_nonnegative_rotation_counter",
        "sessions",
        "refresh_rotation_counter >= 0",
        schema=SCHEMA,
    )

    op.execute(
        "REVOKE ALL ON TABLE ayo.identities, "
        "ayo.identity_authentication_methods, ayo.credential_verifiers, "
        "ayo.authentication_challenges, ayo.identity_devices, ayo.token_families, "
        "ayo.refresh_token_rotations, ayo.recovery_cases FROM PUBLIC"
    )
    op.execute(
        """
        DO $ayo$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE
              ayo.identities, ayo.identity_authentication_methods,
              ayo.credential_verifiers, ayo.authentication_challenges,
              ayo.identity_devices, ayo.token_families,
              ayo.refresh_token_rotations, ayo.recovery_cases TO ayo_runtime;
            REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
              ayo.identities, ayo.identity_authentication_methods,
              ayo.credential_verifiers, ayo.authentication_challenges,
              ayo.identity_devices, ayo.token_families,
              ayo.refresh_token_rotations, ayo.recovery_cases FROM ayo_runtime;
          END IF;
        END $ayo$
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive identity downgrade is prohibited. Apply a reviewed forward fix."
    )
