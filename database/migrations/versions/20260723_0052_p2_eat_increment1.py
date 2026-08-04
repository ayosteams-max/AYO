"""Add P2 AYO Eat Increment 1 availability and order composition.

Revision ID: 20260723_0052
Revises: 20260723_0051
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from BACKEND.persistence.tables import metadata

revision: str = "20260723_0052"
down_revision: str | Sequence[str] | None = "20260723_0051"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "catalogue_modifier_options",
    "p2_eat_availability_policies",
    "p2_eat_availability_policy_history",
    "p2_eat_availability_evaluations",
    "p2_eat_availability_idempotency",
    "p2_eat_availability_outbox",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in NEW_TABLES:
        metadata.tables[f"ayo.{name}"].create(bind)

    op.add_column(
        "commerce_orders",
        sa.Column("availability_evaluation_id", sa.UUID()),
        schema="ayo",
    )
    op.add_column(
        "commerce_orders", sa.Column("composition_hash", sa.String(64)), schema="ayo"
    )
    op.add_column(
        "commerce_orders",
        sa.Column("access_interaction_id", sa.UUID()),
        schema="ayo",
    )
    op.add_column(
        "commerce_order_lines",
        sa.Column(
            "modifier_selections",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="ayo",
    )
    op.add_column(
        "commerce_order_lines",
        sa.Column("customer_instructions", sa.String(500)),
        schema="ayo",
    )

    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID("10000000-0000-4000-8000-000000000056"),
                "code": "eat.availability.manage",
                "description": "Manage PRE-PRODUCTION P2 Eat availability policies.",
                "created_at": now,
            }
        ],
    )
    op.execute(
        """
        CREATE FUNCTION ayo.reject_p2_eat_immutable_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'P2 Eat availability evidence is append-only';
        END $$;
        CREATE TRIGGER trg_p2_eat_policy_history_immutable
          BEFORE UPDATE OR DELETE ON ayo.p2_eat_availability_policy_history
          FOR EACH ROW EXECUTE FUNCTION
          ayo.reject_p2_eat_immutable_evidence_mutation();
        CREATE TRIGGER trg_p2_eat_evaluations_immutable
          BEFORE UPDATE OR DELETE ON ayo.p2_eat_availability_evaluations
          FOR EACH ROW EXECUTE FUNCTION
          ayo.reject_p2_eat_immutable_evidence_mutation();
        """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE ON
          ayo.p2_eat_availability_policies,
          ayo.p2_eat_availability_idempotency
        TO ayo_runtime;
        GRANT SELECT, INSERT ON
          ayo.p2_eat_availability_policy_history,
          ayo.p2_eat_availability_evaluations,
          ayo.p2_eat_availability_outbox
        TO ayo_runtime;
        GRANT SELECT ON ayo.catalogue_modifier_options TO ayo_runtime;
        GRANT SELECT, INSERT ON ayo.commerce_orders, ayo.commerce_order_lines
        TO ayo_runtime;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_p2_eat_evaluations_immutable
          ON ayo.p2_eat_availability_evaluations;
        DROP TRIGGER IF EXISTS trg_p2_eat_policy_history_immutable
          ON ayo.p2_eat_availability_policy_history;
        DROP FUNCTION IF EXISTS ayo.reject_p2_eat_immutable_evidence_mutation();
        """
    )
    op.drop_column("commerce_order_lines", "customer_instructions", schema="ayo")
    op.drop_column("commerce_order_lines", "modifier_selections", schema="ayo")
    op.drop_column("commerce_orders", "access_interaction_id", schema="ayo")
    op.drop_column("commerce_orders", "composition_hash", schema="ayo")
    op.drop_column("commerce_orders", "availability_evaluation_id", schema="ayo")
    for name in reversed(NEW_TABLES):
        op.drop_table(name, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code = 'eat.availability.manage'")
