"""Create the policy-shaped RBAC authorization foundation.

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15

This revision is immutable after application to any shared environment.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0005"
down_revision: str | Sequence[str] | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "ayo"


def upgrade() -> None:
    registered_at = datetime.now(UTC)
    op.create_table(
        "permissions",
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(63), nullable=False),
        sa.Column("description", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[a-z][a-z0-9_.-]{2,62}$'", name="ck_permissions_valid_code"
        ),
        sa.PrimaryKeyConstraint("permission_id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
        schema=SCHEMA,
    )
    op.create_table(
        "roles",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(63), nullable=False),
        sa.Column("description", sa.String(256), nullable=False),
        sa.Column(
            "system_managed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[a-z][a-z0-9_.-]{2,62}$'", name="ck_roles_valid_code"
        ),
        sa.CheckConstraint("version > 0", name="ck_roles_positive_version"),
        sa.PrimaryKeyConstraint("role_id", name="pk_roles"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
        schema=SCHEMA,
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["ayo.permissions.permission_id"],
            name="fk_role_permissions_permission_id_permissions",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["ayo.roles.role_id"],
            name="fk_role_permissions_role_id_roles",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_role_permissions_permission",
        "role_permissions",
        ["permission_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "identity_role_assignments",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_by_identity_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_identity_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("revocation_reason", sa.String(63), nullable=True),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_identity_id IS NULL AND "
            "revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND "
            "revoked_by_identity_id IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_identity_role_assignments_consistent_revocation",
        ),
        sa.CheckConstraint(
            "revocation_reason IS NULL OR "
            "revocation_reason ~ '^[a-z][a-z0-9_.-]{2,62}$'",
            name="ck_identity_role_assignments_safe_revocation_reason",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > assigned_at",
            name="ck_identity_role_assignments_valid_lifetime",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["ayo.identities.identity_id"],
            name="fk_identity_role_assignments_identity_id_identities",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["ayo.roles.role_id"],
            name="fk_identity_role_assignments_role_id_roles",
        ),
        sa.PrimaryKeyConstraint("assignment_id", name="pk_identity_role_assignments"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_identity_role_assignments_identity_active",
        "identity_role_assignments",
        ["identity_id", "role_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_identity_role_assignments_role",
        "identity_role_assignments",
        ["role_id"],
        schema=SCHEMA,
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-00000000000{index}",
                "code": code,
                "description": description,
                "created_at": registered_at,
            }
            for index, (code, description) in enumerate(
                (
                    (
                        "authorization.permissions.read",
                        "Read the authorization permission registry.",
                    ),
                    (
                        "authorization.roles.read",
                        "Read authorization roles and their grants.",
                    ),
                    (
                        "authorization.roles.manage",
                        "Create roles and manage role permissions.",
                    ),
                    (
                        "authorization.assignments.read",
                        "Read identity role assignments.",
                    ),
                    (
                        "authorization.assignments.manage",
                        "Assign and revoke identity roles.",
                    ),
                ),
                start=1,
            )
        ],
    )

    op.execute(
        "REVOKE ALL ON TABLE ayo.permissions, ayo.roles, ayo.role_permissions, "
        "ayo.identity_role_assignments FROM PUBLIC"
    )
    op.execute(
        """
        DO $ayo$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
            GRANT SELECT ON TABLE ayo.permissions TO ayo_runtime;
            GRANT SELECT, INSERT, UPDATE ON TABLE ayo.roles TO ayo_runtime;
            GRANT SELECT, INSERT ON TABLE ayo.role_permissions TO ayo_runtime;
            GRANT SELECT, INSERT, UPDATE ON TABLE
              ayo.identity_role_assignments TO ayo_runtime;
            REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
              ayo.permissions, ayo.roles, ayo.role_permissions,
              ayo.identity_role_assignments FROM ayo_runtime;
          END IF;
        END $ayo$
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive authorization downgrade is prohibited. Apply a reviewed "
        "forward fix."
    )
