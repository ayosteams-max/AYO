"""Add Request Access & Interaction Provenance Increment 1.

Revision ID: 20260723_0051
Revises: 20260723_0050
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260723_0051"
down_revision: str | Sequence[str] | None = "20260723_0050"
branch_labels = None
depends_on = None

TABLES = (
    "request_access_source_adapters",
    "request_access_channel_capabilities",
    "request_access_continuity_references",
    "request_access_interaction_provenance",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)

    now = datetime.now(UTC)
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": permission_id,
                "code": code,
                "description": description,
                "created_at": now,
            }
            for permission_id, code, description in (
                (
                    "10000000-0000-4000-8000-000000000053",
                    "access.provenance.manage",
                    "Manage PRE-PRODUCTION adapter and capability declarations.",
                ),
                (
                    "10000000-0000-4000-8000-000000000054",
                    "access.provenance.record",
                    "Record accepted PRE-PRODUCTION interaction provenance.",
                ),
                (
                    "10000000-0000-4000-8000-000000000055",
                    "access.provenance.support",
                    "Record approved support-assisted interaction provenance.",
                ),
            )
        ],
    )

    op.execute(
        """
        CREATE FUNCTION ayo.reject_request_access_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'request access evidence is append-only';
        END $$;
        CREATE TRIGGER trg_request_access_adapter_immutable
          BEFORE UPDATE OR DELETE ON ayo.request_access_source_adapters
          FOR EACH ROW EXECUTE FUNCTION
            ayo.reject_request_access_evidence_mutation();
        CREATE TRIGGER trg_request_access_continuity_immutable
          BEFORE UPDATE OR DELETE ON ayo.request_access_continuity_references
          FOR EACH ROW EXECUTE FUNCTION
            ayo.reject_request_access_evidence_mutation();
        CREATE TRIGGER trg_request_access_provenance_immutable
          BEFORE UPDATE OR DELETE ON ayo.request_access_interaction_provenance
          FOR EACH ROW EXECUTE FUNCTION
            ayo.reject_request_access_evidence_mutation();
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
            GRANT SELECT, INSERT ON
              ayo.request_access_source_adapters,
              ayo.request_access_continuity_references,
              ayo.request_access_interaction_provenance
            TO ayo_runtime;
            GRANT SELECT, INSERT, UPDATE ON
              ayo.request_access_channel_capabilities
            TO ayo_runtime;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Forward-only migration: Request Access provenance must be preserved"
    )
