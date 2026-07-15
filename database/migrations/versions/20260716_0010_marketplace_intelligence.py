"""Add deterministic marketplace intelligence authority.

Revision ID: 20260716_0010
Revises: 20260716_0009
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0010"
down_revision: str | Sequence[str] | None = "20260716_0009"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    op.create_table(
        "marketplace_rule_sets",
        sa.Column("rule_set_id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.String(63), nullable=False, unique=True),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("configuration_checksum", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version ~ '^[a-z][a-z0-9_.-]{1,62}$'",
            name="ck_marketplace_rule_sets_marketplace_rule_valid_version",
        ),
        sa.CheckConstraint(
            "configuration_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_marketplace_rule_sets_marketplace_rule_valid_checksum",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "marketplace_decisions",
        sa.Column("decision_id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "rule_set_id",
            sa.Uuid(),
            sa.ForeignKey("ayo.marketplace_rule_sets.rule_set_id"),
            nullable=False,
        ),
        sa.Column("market_code", sa.String(63), nullable=False),
        sa.Column("zone_code", sa.String(63), nullable=False),
        sa.Column("service_type", sa.String(63), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recommendation", sa.String(32), nullable=False),
        sa.Column("health_score_bps", sa.Integer(), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "rule_set_id",
            name="uq_marketplace_decision_snapshot_rule",
        ),
        sa.CheckConstraint(
            "health_score_bps BETWEEN 0 AND 10000",
            name="ck_marketplace_decisions_marketplace_decision_valid_health",
        ),
        sa.CheckConstraint(
            "recommendation IN ('no_change','supply_guidance','incentive_review',"
            "'price_review','suppress','insufficient_data')",
            name="ck_marketplace_decisions_marketplace_decision_valid_recommendation",
        ),
        sa.CheckConstraint(
            "expires_at > generated_at",
            name="ck_marketplace_decisions_marketplace_decision_lifetime",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_marketplace_decisions_market_window",
        "marketplace_decisions",
        ["market_code", "zone_code", "window_ended_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "marketplace_simulation_runs",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("baseline_rule_version", sa.String(63), nullable=False),
        sa.Column("candidate_rule_version", sa.String(63), nullable=False),
        sa.Column("dataset_checksum", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dataset_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_marketplace_simulation_runs_marketplace_simulation_valid_checksum",
        ),
        schema=SCHEMA,
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
            GRANT SELECT ON ayo.marketplace_rule_sets TO ayo_runtime;
            GRANT SELECT, INSERT ON ayo.marketplace_decisions TO ayo_runtime;
            GRANT SELECT, INSERT ON ayo.marketplace_simulation_runs TO ayo_runtime;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayo_runtime') THEN
            REVOKE ALL ON ayo.marketplace_simulation_runs FROM ayo_runtime;
            REVOKE ALL ON ayo.marketplace_decisions FROM ayo_runtime;
            REVOKE ALL ON ayo.marketplace_rule_sets FROM ayo_runtime;
          END IF;
        END
        $$
        """
    )
    op.drop_table("marketplace_simulation_runs", schema=SCHEMA)
    op.drop_index(
        "ix_marketplace_decisions_market_window",
        table_name="marketplace_decisions",
        schema=SCHEMA,
    )
    op.drop_table("marketplace_decisions", schema=SCHEMA)
    op.drop_table("marketplace_rule_sets", schema=SCHEMA)
