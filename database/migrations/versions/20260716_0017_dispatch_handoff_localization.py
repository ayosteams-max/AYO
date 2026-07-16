"""Immediate dispatch handoff and global localization foundation.

Revision ID: 20260716_0017
Revises: 20260716_0016
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision = "20260716_0017"
down_revision: str | Sequence[str] | None = "20260716_0016"
branch_labels = None
depends_on = None
TABLES = (
    "immediate_dispatch_handoffs",
    "immediate_dispatch_candidate_sets",
    "immediate_dispatch_offers",
    "immediate_dispatch_assignments",
    "immediate_dispatch_idempotency",
    "immediate_dispatch_events",
    "immediate_dispatch_outbox",
    "localization_preferences",
    "localization_pack_manifests",
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
            "59",
            "dispatch.handoff.receive",
            "Receive an authenticated internal canonical request handoff.",
        ),
        (
            "60",
            "dispatch.handoff.worker",
            "Run bounded Immediate Dispatch handoff work.",
        ),
        (
            "61",
            "localization.preference.read_own",
            "Read the authenticated identity's language preference.",
        ),
        (
            "62",
            "localization.preference.update_own",
            "Update the authenticated identity's language preference.",
        ),
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
    GRANT SELECT, INSERT ON ayo.immediate_dispatch_handoffs,
      ayo.immediate_dispatch_candidate_sets, ayo.immediate_dispatch_offers,
      ayo.immediate_dispatch_assignments, ayo.immediate_dispatch_idempotency,
      ayo.immediate_dispatch_events, ayo.immediate_dispatch_outbox,
      ayo.localization_preferences TO ayo_runtime;
    GRANT SELECT ON ayo.localization_pack_manifests TO ayo_runtime;
    GRANT UPDATE ON ayo.immediate_dispatch_handoffs, ayo.immediate_dispatch_offers,
      ayo.immediate_dispatch_assignments, ayo.immediate_dispatch_outbox,
      ayo.localization_preferences TO ayo_runtime;
    END IF; END $$;""")


def downgrade() -> None:
    op.execute(
        "DELETE FROM ayo.role_permissions WHERE permission_id IN (SELECT permission_id FROM ayo.permissions WHERE code IN ('dispatch.handoff.receive','dispatch.handoff.worker','localization.preference.read_own','localization.preference.update_own'))"
    )
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('dispatch.handoff.receive','dispatch.handoff.worker','localization.preference.read_own','localization.preference.update_own')"
    )
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind)
