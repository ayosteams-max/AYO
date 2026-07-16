"""Mission 20 arrival, readiness and waiting evidence persistence.

Revision ID: 20260716_0014
Revises: 20260716_0013
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260716_0014"
down_revision: str | Sequence[str] | None = "20260716_0013"
branch_labels = None
depends_on = None

TABLES = (
    "arrival_evaluations",
    "rider_readiness_decisions",
    "waiting_policy_snapshots",
    "waiting_sessions",
    "waiting_session_events",
    "arrival_notification_evidence",
    "consequence_suppression_decisions",
    "arrival_waiting_idempotency",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)
    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
        GRANT SELECT, INSERT ON ayo.arrival_evaluations,
          ayo.rider_readiness_decisions, ayo.waiting_policy_snapshots,
          ayo.waiting_sessions, ayo.waiting_session_events,
          ayo.arrival_notification_evidence, ayo.consequence_suppression_decisions,
          ayo.arrival_waiting_idempotency TO ayo_runtime;
        GRANT UPDATE ON ayo.waiting_sessions TO ayo_runtime;
        END IF; END $$"""
    )
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    values = (
        ("46", "arrival_waiting.read", "Read an owned arrival and waiting projection."),
        (
            "47",
            "arrival_waiting.rider.command",
            "Submit an owned rider arrival/waiting command.",
        ),
        (
            "48",
            "arrival_waiting.driver.command",
            "Submit an assigned driver arrival/waiting command.",
        ),
        (
            "49",
            "arrival_waiting.worker.run",
            "Run bounded arrival/waiting recovery work.",
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


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM ayo.permissions WHERE code LIKE 'arrival_waiting.%')"
    )
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'arrival_waiting.%'")
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
