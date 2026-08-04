"""Add R1 Service Area and Ride Product Availability foundation.

Revision ID: 20260723_0050
Revises: 20260723_0049
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260723_0050"
down_revision: str | Sequence[str] | None = "20260723_0049"
branch_labels = None
depends_on = None

TABLES = (
    "mobility_service_areas",
    "mobility_service_area_geometries",
    "mobility_ride_products",
    "mobility_product_availability",
    "mobility_availability_evaluations",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)

    now = datetime.now(UTC)
    products = sa.table(
        "mobility_ride_products",
        sa.column("product_code", sa.String()),
        sa.column("display_key", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    op.bulk_insert(
        products,
        [
            {
                "product_code": code,
                "display_key": f"mobility.product.{code}",
                "created_at": now,
            }
            for code in (
                "standard",
                "premium",
                "airport_transfer",
                "accessible_private_ride",
            )
        ],
    )

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
                    "10000000-0000-4000-8000-000000000050",
                    "mobility.service_area.create",
                    "Create a PRE-PRODUCTION planned passenger-mobility service area.",
                ),
                (
                    "10000000-0000-4000-8000-000000000051",
                    "mobility.service_area.manage",
                    "Manage PRE-PRODUCTION service-area and product availability.",
                ),
                (
                    "10000000-0000-4000-8000-000000000052",
                    "mobility.service_area.evaluate",
                    "Evaluate passenger-mobility service availability.",
                ),
            )
        ],
    )

    op.execute(
        """
        CREATE FUNCTION ayo.reject_mobility_availability_history_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'mobility availability history is append-only';
        END $$;
        CREATE TRIGGER trg_mobility_geometry_immutable
          BEFORE UPDATE OR DELETE ON ayo.mobility_service_area_geometries
          FOR EACH ROW EXECUTE FUNCTION
            ayo.reject_mobility_availability_history_mutation();
        CREATE TRIGGER trg_mobility_evaluation_immutable
          BEFORE UPDATE OR DELETE ON ayo.mobility_availability_evaluations
          FOR EACH ROW EXECUTE FUNCTION
            ayo.reject_mobility_availability_history_mutation();
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON
              ayo.mobility_service_areas,
              ayo.mobility_product_availability
            TO ayo_runtime;
            GRANT SELECT, INSERT ON
              ayo.mobility_service_area_geometries,
              ayo.mobility_availability_evaluations
            TO ayo_runtime;
            GRANT SELECT ON ayo.mobility_ride_products TO ayo_runtime;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Forward-only migration: Service Area geometry and evaluation history "
        "must be preserved"
    )
