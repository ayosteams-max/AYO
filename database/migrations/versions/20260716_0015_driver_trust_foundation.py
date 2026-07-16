"""Driver identity, onboarding, vehicle and eligibility foundation.

Revision ID: 20260716_0015
Revises: 20260716_0014
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260716_0015"
down_revision: str | Sequence[str] | None = "20260716_0014"
branch_labels = None
depends_on = None

TABLES = (
    "driver_onboarding_cases",
    "driver_vehicles",
    "driver_document_evidence",
    "driver_vehicle_authorizations",
    "driver_eligibility_decisions",
    "driver_trust_idempotency",
    "driver_trust_events",
    "driver_trust_outbox",
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
            "50",
            "driver_trust.read_own",
            "Read the authenticated driver's onboarding projection.",
        ),
        (
            "51",
            "driver_trust.evidence.read_own",
            "Read privacy-minimised own evidence metadata.",
        ),
        (
            "52",
            "driver_trust.evidence.read_sensitive",
            "Read separately authorized sensitive evidence metadata.",
        ),
        (
            "53",
            "driver_trust.review",
            "Perform an authorized operations review decision.",
        ),
        ("54", "driver_trust.appeal.review", "Review a linked driver identity appeal."),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-0000000000{s}",
                "code": c,
                "description": d,
                "created_at": datetime.now(UTC),
            }
            for s, c, d in values
        ],
    )
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
      GRANT SELECT, INSERT ON ayo.driver_onboarding_cases, ayo.driver_document_evidence,
        ayo.driver_vehicles, ayo.driver_vehicle_authorizations, ayo.driver_eligibility_decisions,
        ayo.driver_trust_idempotency, ayo.driver_trust_events, ayo.driver_trust_outbox TO ayo_runtime;
      GRANT UPDATE ON ayo.driver_onboarding_cases, ayo.driver_document_evidence,
        ayo.driver_vehicles, ayo.driver_vehicle_authorizations, ayo.driver_trust_outbox TO ayo_runtime;
    END IF; END $$""")


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'driver_trust.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'driver_trust.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
