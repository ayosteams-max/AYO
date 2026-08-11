"""Immediate Standard cash-ride bounded certification repair.

Revision ID: 20260811_0059
Revises: 20260806_0058
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0059"
down_revision: str | Sequence[str] | None = "20260806_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "post_trip_records",
        sa.Column("cash_evidence_state", sa.String(32)),
        schema="ayo",
    )
    for name in ("fare_estimate_id", "estimate_acceptance_id"):
        op.add_column("booking_confirmations", sa.Column(name, sa.UUID()), schema="ayo")
    op.add_column(
        "booking_confirmations",
        sa.Column("pricing_lineage_hash", sa.String(64)),
        schema="ayo",
    )
    op.create_foreign_key(
        "fk_booking_confirmation_fare_estimate",
        "booking_confirmations",
        "fare_estimates",
        ["fare_estimate_id"],
        ["estimate_id"],
        source_schema="ayo",
        referent_schema="ayo",
    )
    op.create_foreign_key(
        "fk_booking_confirmation_estimate_acceptance",
        "booking_confirmations",
        "fare_estimate_acceptances",
        ["estimate_acceptance_id"],
        ["acceptance_id"],
        source_schema="ayo",
        referent_schema="ayo",
    )
    op.create_unique_constraint(
        "uq_booking_confirmation_fare_estimate",
        "booking_confirmations",
        ["fare_estimate_id"],
        schema="ayo",
    )
    op.create_unique_constraint(
        "uq_booking_confirmation_estimate_acceptance",
        "booking_confirmations",
        ["estimate_acceptance_id"],
        schema="ayo",
    )

    for name in (
        "fare_estimate_id",
        "estimate_acceptance_id",
        "pricing_policy_id",
    ):
        op.add_column(
            "immediate_dispatch_handoffs", sa.Column(name, sa.UUID()), schema="ayo"
        )
    op.add_column(
        "immediate_dispatch_handoffs",
        sa.Column("pricing_policy_version", sa.String(63)),
        schema="ayo",
    )
    op.add_column(
        "immediate_dispatch_handoffs",
        sa.Column("pricing_lineage_hash", sa.String(64)),
        schema="ayo",
    )
    for constraint, column, table, target in (
        (
            "fk_handoff_fare_estimate",
            "fare_estimate_id",
            "fare_estimates",
            "estimate_id",
        ),
        (
            "fk_handoff_estimate_acceptance",
            "estimate_acceptance_id",
            "fare_estimate_acceptances",
            "acceptance_id",
        ),
        (
            "fk_handoff_pricing_policy",
            "pricing_policy_id",
            "pricing_policies",
            "policy_id",
        ),
    ):
        op.create_foreign_key(
            constraint,
            "immediate_dispatch_handoffs",
            table,
            [column],
            [target],
            source_schema="ayo",
            referent_schema="ayo",
        )
    op.create_check_constraint(
        "handoff_pricing_lineage_complete",
        "immediate_dispatch_handoffs",
        "(fare_estimate_id IS NULL AND estimate_acceptance_id IS NULL AND pricing_policy_id IS NULL AND pricing_policy_version IS NULL AND pricing_lineage_hash IS NULL) OR "
        "(fare_estimate_id IS NOT NULL AND estimate_acceptance_id IS NOT NULL AND pricing_policy_id IS NOT NULL AND pricing_policy_version IS NOT NULL AND pricing_lineage_hash IS NOT NULL)",
        schema="ayo",
    )

    op.create_table(
        "trip_cash_collection_evidence",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "fare_calculation_id",
            sa.UUID(),
            sa.ForeignKey("ayo.fare_calculations.calculation_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "cash_accounting_policies",
        sa.Column("accounting_policy_id", sa.UUID(), primary_key=True),
        sa.Column(
            "accounting_policy_version", sa.String(63), nullable=False, unique=True
        ),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("accounting_model", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_evidence_hash", sa.String(64), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "trip_cash_accounting_records",
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.active_rides.ride_id"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_id",
            sa.UUID(),
            sa.ForeignKey("ayo.trip_cash_collection_evidence.evidence_id"),
            nullable=False,
        ),
        sa.Column("instruction_id", sa.UUID(), nullable=False, unique=True),
        sa.Column(
            "accounting_policy_id",
            sa.UUID(),
            sa.ForeignKey("ayo.cash_accounting_policies.accounting_policy_id"),
            nullable=False,
        ),
        sa.Column("accounting_policy_version", sa.String(63), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("reconciliation_state", sa.String(24), nullable=False),
        sa.Column(
            "ledger_journal_id",
            sa.UUID(),
            sa.ForeignKey("ayo.ledger_journals.journal_id"),
        ),
        sa.Column(
            "clearing_journal_id",
            sa.UUID(),
            sa.ForeignKey("ayo.ledger_journals.journal_id"),
        ),
        sa.Column("reconciliation_evidence_hash", sa.String(64)),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "version > 0", name="cash_accounting_record_positive_version"
        ),
        schema="ayo",
    )
    op.create_table(
        "cash_reconciliation_evidence",
        sa.Column("reconciliation_evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "ride_id",
            sa.UUID(),
            sa.ForeignKey("ayo.trip_cash_accounting_records.ride_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("accounting_instruction_id", sa.UUID(), nullable=False),
        sa.Column(
            "accounting_policy_id",
            sa.UUID(),
            sa.ForeignKey("ayo.cash_accounting_policies.accounting_policy_id"),
            nullable=False,
        ),
        sa.Column(
            "original_accounting_journal_id",
            sa.UUID(),
            sa.ForeignKey("ayo.ledger_journals.journal_id"),
            nullable=False,
        ),
        sa.Column("evidence_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )


def downgrade() -> None:
    op.drop_table("cash_reconciliation_evidence", schema="ayo")
    op.drop_table("trip_cash_accounting_records", schema="ayo")
    op.drop_table("cash_accounting_policies", schema="ayo")
    op.drop_table("trip_cash_collection_evidence", schema="ayo")
    op.drop_constraint(
        "handoff_pricing_lineage_complete",
        "immediate_dispatch_handoffs",
        schema="ayo",
        type_="check",
    )
    for constraint in (
        "fk_handoff_pricing_policy",
        "fk_handoff_estimate_acceptance",
        "fk_handoff_fare_estimate",
    ):
        op.drop_constraint(
            constraint,
            "immediate_dispatch_handoffs",
            schema="ayo",
            type_="foreignkey",
        )
    for name in (
        "pricing_lineage_hash",
        "pricing_policy_version",
        "pricing_policy_id",
        "estimate_acceptance_id",
        "fare_estimate_id",
    ):
        op.drop_column("immediate_dispatch_handoffs", name, schema="ayo")
    op.drop_constraint(
        "uq_booking_confirmation_estimate_acceptance",
        "booking_confirmations",
        schema="ayo",
        type_="unique",
    )
    op.drop_constraint(
        "uq_booking_confirmation_fare_estimate",
        "booking_confirmations",
        schema="ayo",
        type_="unique",
    )
    op.drop_constraint(
        "fk_booking_confirmation_estimate_acceptance",
        "booking_confirmations",
        schema="ayo",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_booking_confirmation_fare_estimate",
        "booking_confirmations",
        schema="ayo",
        type_="foreignkey",
    )
    for name in (
        "pricing_lineage_hash",
        "estimate_acceptance_id",
        "fare_estimate_id",
    ):
        op.drop_column("booking_confirmations", name, schema="ayo")
    op.drop_column("post_trip_records", "cash_evidence_state", schema="ayo")
