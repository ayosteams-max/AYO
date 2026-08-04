"""Enforce one canonical identity per authentication lookup.

Revision ID: 20260720_0028
Revises: 20260718_0027
Create Date: 2026-07-20

This revision is immutable after application to any shared environment.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260720_0028"
down_revision: str | Sequence[str] | None = "20260718_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $ayo$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM ayo.identity_authentication_methods
            WHERE lookup_reference IS NOT NULL
            GROUP BY method_type, lookup_reference
            HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION
              'Duplicate authentication lookups require reviewed identity reconciliation';
          END IF;
        END $ayo$
        """
    )
    op.create_index(
        "uq_identity_auth_methods_type_lookup",
        "identity_authentication_methods",
        ["method_type", "lookup_reference"],
        unique=True,
        schema="ayo",
        postgresql_where="lookup_reference IS NOT NULL",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Removing canonical authentication uniqueness is prohibited; apply a forward fix"
    )
