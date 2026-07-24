"""Add bounded identity administrative security and recovery.

Revision ID: 20260723_0047
Revises: 20260723_0046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0047"
down_revision: str | Sequence[str] | None = "20260723_0046"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.add_column(
        "identity_accounts",
        sa.Column("failed_window_started_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.add_column(
        "identity_accounts",
        sa.Column(
            "credential_change_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "identity_accounts",
        sa.Column("credential_change_reason", sa.String(63)),
        schema=SCHEMA,
    )
    op.add_column(
        "identity_accounts",
        sa.Column("credential_change_provenance", sa.String(63)),
        schema=SCHEMA,
    )
    op.create_table(
        "identity_security_bootstrap",
        sa.Column("bootstrap_key", sa.String(32), nullable=False),
        sa.Column(
            "target_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identity_accounts.account_id"),
            nullable=False,
        ),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(63), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("bootstrap_key", name="pk_identity_security_bootstrap"),
        sa.CheckConstraint(
            "bootstrap_key = 'first_platform_administrator'",
            name="ck_identity_security_bootstrap_singleton_key",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "account_recovery_tokens",
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identity_accounts.account_id"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("token_id", name="pk_account_recovery_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_account_recovery_tokens_token_hash"),
        sa.UniqueConstraint(
            "account_id",
            "purpose",
            "token_version",
            name="uq_account_recovery_tokens_account_id",
        ),
        sa.CheckConstraint(
            "purpose = 'password_recovery'",
            name="ck_account_recovery_tokens_valid_purpose",
        ),
        sa.CheckConstraint(
            "state IN ('active','consumed','revoked','superseded')",
            name="ck_account_recovery_tokens_valid_state",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_account_recovery_tokens_valid_lifetime"
        ),
        sa.CheckConstraint(
            "token_version > 0 AND version > 0",
            name="ck_account_recovery_tokens_positive_versions",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_account_recovery_tokens_active",
        "account_recovery_tokens",
        ["account_id", "purpose"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_table(
        "authentication_origin_windows",
        sa.Column("origin_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("throttled_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("origin_hash", name="pk_authentication_origin_windows"),
        sa.CheckConstraint(
            "attempt_count > 0 AND version > 0",
            name="ck_authentication_origin_windows_positive_counts",
        ),
        schema=SCHEMA,
    )
    op.execute("""
      INSERT INTO ayo.permissions(permission_id,code,description,created_at) VALUES
      ('a1000000-0000-4000-8000-000000000008','identity.account.force_credential_change','Require credential replacement',now()),
      ('a1000000-0000-4000-8000-000000000009','identity.session.revoke_any','Revoke another Account session',now()),
      ('a1000000-0000-4000-8000-000000000010','identity.recovery.revoke','Revoke recovery instruments',now()),
      ('a1000000-0000-4000-8000-000000000011','identity.role.assign','Assign approved platform roles',now()),
      ('a1000000-0000-4000-8000-000000000012','identity.role.remove','Remove approved platform roles',now()),
      ('a1000000-0000-4000-8000-000000000013','identity.bootstrap.execute','Execute separately approved bootstrap tooling',now())
      ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
      INSERT INTO ayo.role_permissions(role_id,permission_id,granted_at)
      SELECT r.role_id,p.permission_id,now() FROM ayo.roles r CROSS JOIN ayo.permissions p
      WHERE r.code='platform_administrator' AND p.code IN
      ('identity.account.force_credential_change','identity.session.revoke_any','identity.recovery.revoke','identity.role.assign','identity.role.remove')
      ON CONFLICT DO NOTHING
    """)
    for table in (
        "identity_security_bootstrap",
        "account_recovery_tokens",
        "authentication_origin_windows",
    ):
        op.execute(f"REVOKE ALL ON ayo.{table} FROM PUBLIC")
    op.execute("""
      DO $ayo$
      BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
          GRANT SELECT, INSERT, UPDATE ON ayo.account_password_credentials TO ayo_runtime;
          GRANT SELECT, INSERT, UPDATE ON ayo.account_sessions TO ayo_runtime;
          GRANT SELECT, INSERT, UPDATE ON ayo.account_role_assignments TO ayo_runtime;
          GRANT SELECT, INSERT ON ayo.identity_security_bootstrap TO ayo_runtime;
          GRANT SELECT, INSERT, UPDATE ON ayo.account_recovery_tokens TO ayo_runtime;
          GRANT SELECT, INSERT, UPDATE ON ayo.authentication_origin_windows TO ayo_runtime;
          REVOKE DELETE, TRUNCATE ON ayo.account_password_credentials, ayo.account_sessions,
            ayo.account_role_assignments, ayo.identity_security_bootstrap,
            ayo.account_recovery_tokens, ayo.authentication_origin_windows FROM ayo_runtime;
        END IF;
      END
      $ayo$
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive identity-security downgrade is prohibited; use a reviewed forward fix."
    )
