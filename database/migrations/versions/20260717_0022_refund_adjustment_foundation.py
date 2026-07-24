"""Refund & Adjustment Foundation.

Revision ID: 20260717_0022
Revises: 20260717_0021
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260717_0022"
down_revision: str | Sequence[str] | None = "20260717_0021"
branch_labels = None
depends_on = None
TABLES = (
    "refund_requests",
    "refund_decisions",
    "refund_authorizations",
    "refund_evidence",
    "refund_events",
    "refund_outbox",
    "refund_idempotency",
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
            "87",
            "refund.request.create",
            "Create an immutable refund or adjustment request for an owned ride payment.",
        ),
        (
            "88",
            "refund.review.perform",
            "Perform support review transitions on a refund request.",
        ),
        (
            "89",
            "refund.investigation.perform",
            "Record risk investigation findings and evidence on a refund request.",
        ),
        (
            "90",
            "refund.approve",
            "Approve refund requests for finance-authorized outcomes.",
        ),
        (
            "91",
            "refund.schedule",
            "Schedule approved refund requests for bounded workflow completion.",
        ),
        (
            "92",
            "refund.workflow.run",
            "Execute bounded service-side completion transitions.",
        ),
        (
            "93",
            "refund.trace.read",
            "Read immutable refund requests, decisions, authorizations, and evidence.",
        ),
        (
            "94",
            "support.refund.read_status",
            "Read refund request status without mutation authority.",
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

    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
    GRANT SELECT, INSERT ON ayo.refund_requests, ayo.refund_decisions,
      ayo.refund_authorizations, ayo.refund_evidence,
      ayo.refund_events, ayo.refund_outbox, ayo.refund_idempotency TO ayo_runtime;
    GRANT UPDATE ON ayo.refund_requests, ayo.refund_outbox TO ayo_runtime;
    END IF; END $$;"""
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code LIKE 'refund.%' OR code = 'support.refund.read_status')"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code LIKE 'refund.%' OR code = 'support.refund.read_status'"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
