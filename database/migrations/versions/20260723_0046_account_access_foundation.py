"""Add account-native credentials, sessions and platform RBAC.

Revision ID: 20260723_0046
Revises: 20260723_0045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0046"
down_revision: str | Sequence[str] | None = "20260723_0045"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.add_column(
        "identity_accounts",
        sa.Column(
            "failed_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "identity_accounts",
        sa.Column("last_failed_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_identity_accounts_nonnegative_failed_attempts",
        "identity_accounts",
        "failed_attempt_count >= 0",
        schema=SCHEMA,
    )
    op.create_table(
        "account_password_credentials",
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identity_accounts.account_id"),
            nullable=False,
        ),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("scheme", sa.String(32), nullable=False),
        sa.Column("verifier", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint(
            "credential_id", name="pk_account_password_credentials"
        ),
        sa.UniqueConstraint(
            "account_id",
            "credential_version",
            name="uq_account_password_credentials_account_id",
        ),
        sa.CheckConstraint(
            "credential_version > 0",
            name="ck_account_password_credentials_positive_credential_version",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_account_password_credentials_active",
        "account_password_credentials",
        ["account_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "account_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identity_accounts.account_id"),
            nullable=False,
        ),
        sa.Column("client_reference", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inactivity_seconds", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.String(63)),
        sa.Column("rotated_from_session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name="pk_account_sessions"),
        sa.CheckConstraint(
            "inactivity_seconds > 0",
            name="ck_account_sessions_positive_inactivity_seconds",
        ),
        sa.CheckConstraint(
            "absolute_expires_at > created_at",
            name="ck_account_sessions_valid_absolute_lifetime",
        ),
        sa.CheckConstraint("version > 0", name="ck_account_sessions_positive_version"),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_account_sessions_consistent_revocation",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_account_sessions_account_active",
        "account_sessions",
        ["account_id", "revoked_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "account_role_assignments",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identity_accounts.account_id"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.roles.role_id"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ayo.identity_accounts.account_id"),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_account_id", postgresql.UUID(as_uuid=True)),
        sa.Column("revocation_reason", sa.String(63)),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("assignment_id", name="pk_account_role_assignments"),
        sa.CheckConstraint(
            "version > 0", name="ck_account_role_assignments_positive_version"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_account_role_assignments_active",
        "account_role_assignments",
        ["account_id", "role_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.execute("""
        INSERT INTO ayo.permissions(permission_id, code, description, created_at) VALUES
        ('a1000000-0000-4000-8000-000000000001','identity.account.activate','Activate a pending platform account',now()),
        ('a1000000-0000-4000-8000-000000000002','identity.account.suspend','Suspend a platform account',now()),
        ('a1000000-0000-4000-8000-000000000003','identity.account.unlock','Unlock a locked platform account',now()),
        ('a1000000-0000-4000-8000-000000000004','identity.account.close','Close a platform account',now()),
        ('a1000000-0000-4000-8000-000000000005','identity.roles.manage','Assign and remove platform roles',now()),
        ('a1000000-0000-4000-8000-000000000006','identity.sessions.revoke','Revoke platform sessions',now()),
        ('a1000000-0000-4000-8000-000000000007','identity.ownership.override','Apply an explicit administrative ownership override',now())
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO ayo.roles(role_id, code, description, system_managed, created_at, version) VALUES
        ('a2000000-0000-4000-8000-000000000001','authenticated_user','Authenticated platform account',true,now(),1),
        ('a2000000-0000-4000-8000-000000000002','platform_support','Bounded platform support',true,now(),1),
        ('a2000000-0000-4000-8000-000000000003','platform_administrator','Platform identity administration',true,now(),1)
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO ayo.role_permissions(role_id, permission_id, granted_at)
        SELECT r.role_id, p.permission_id, now() FROM ayo.roles r CROSS JOIN ayo.permissions p
        WHERE r.code='platform_administrator' AND p.code IN
        ('identity.account.activate','identity.account.suspend','identity.account.unlock','identity.account.close','identity.roles.manage','identity.sessions.revoke','identity.ownership.override')
        ON CONFLICT DO NOTHING
    """)
    for table in (
        "account_password_credentials",
        "account_sessions",
        "account_role_assignments",
    ):
        op.execute(f"REVOKE ALL ON ayo.{table} FROM PUBLIC")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive account-access downgrade is prohibited; use a reviewed forward fix."
    )
