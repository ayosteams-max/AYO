"""Versioned ETB Pricing and fare calculation foundation.

Revision ID: 20260716_0019
Revises: 20260716_0018
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260716_0019"
down_revision: str | Sequence[str] | None = "20260716_0018"
branch_labels = None
depends_on = None
TABLES = (
    "pricing_policies",
    "fare_estimates",
    "fare_estimate_acceptances",
    "fare_calculations",
    "pricing_calculation_components",
    "pricing_idempotency",
    "pricing_events",
    "pricing_outbox",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    values = (
        (
            "64",
            "pricing.policy.manage",
            "Create and approve immutable pricing policy versions.",
        ),
        (
            "65",
            "pricing.policy.publish",
            "Publish a checker-approved pricing policy version.",
        ),
        (
            "66",
            "pricing.estimate.create",
            "Create an owned Immediate Standard ETB estimate.",
        ),
        ("67", "pricing.estimate.accept", "Accept an owned unexpired fare estimate."),
        (
            "68",
            "pricing.final.calculate",
            "Calculate a final fare from a completed canonical ride.",
        ),
        (
            "69",
            "pricing.breakdown.read_own",
            "Read an authorized role-safe pricing breakdown.",
        ),
        (
            "70",
            "pricing.trace.read",
            "Read an authorized immutable financial journey projection.",
        ),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-0000000000{suffix}",
                "code": code,
                "description": description,
                "created_at": datetime.now(UTC),
            }
            for suffix, code, description in values
        ],
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
    GRANT SELECT, INSERT ON ayo.fare_estimates, ayo.fare_estimate_acceptances,
      ayo.fare_calculations, ayo.pricing_calculation_components,
      ayo.pricing_idempotency, ayo.pricing_events, ayo.pricing_outbox TO ayo_runtime;
    GRANT SELECT ON ayo.pricing_policies TO ayo_runtime;
    GRANT UPDATE ON ayo.pricing_outbox TO ayo_runtime;
    END IF; END $$;""")


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'pricing.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'pricing.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
