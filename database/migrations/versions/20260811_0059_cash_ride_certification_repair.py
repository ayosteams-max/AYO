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

AYO_SCHEMA = "ayo"


def _type_signature(column_type: sa.types.TypeEngine) -> tuple[str, int | None]:
    if isinstance(column_type, sa.Uuid):
        return ("uuid", None)
    if isinstance(column_type, sa.String):
        return ("string", column_type.length)
    return (column_type.__class__.__name__.lower(), None)


def _ensure_nullable_columns(
    table_name: str,
    columns: Sequence[sa.Column],
) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {
        column["name"]: column
        for column in inspector.get_columns(table_name, schema=AYO_SCHEMA)
    }
    for column in columns:
        current = existing.get(column.name)
        if current is None:
            op.add_column(table_name, column, schema=AYO_SCHEMA)
            continue
        expected_type = _type_signature(column.type)
        actual_type = _type_signature(current["type"])
        if actual_type != expected_type or current["nullable"] is not True:
            raise RuntimeError(
                "Migration 0059 found incompatible existing column "
                f"{AYO_SCHEMA}.{table_name}.{column.name}: "
                f"type={actual_type!r}, nullable={current['nullable']!r}; "
                f"expected type={expected_type!r}, nullable=True"
            )


def _ensure_foreign_key(
    *,
    name: str,
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
) -> None:
    expected = {
        "constrained_columns": [source_column],
        "referred_schema": AYO_SCHEMA,
        "referred_table": target_table,
        "referred_columns": [target_column],
    }
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys(
        source_table, schema=AYO_SCHEMA
    )
    named = [foreign_key for foreign_key in foreign_keys if foreign_key["name"] == name]
    same_column = [
        foreign_key
        for foreign_key in foreign_keys
        if foreign_key["constrained_columns"] == [source_column]
    ]
    if named:
        if len(named) != 1 or any(
            named[0].get(key) != value for key, value in expected.items()
        ):
            raise RuntimeError(f"Migration 0059 found incompatible foreign key {name}")
        if len(same_column) != 1:
            raise RuntimeError(
                "Migration 0059 found duplicate foreign keys for "
                f"{AYO_SCHEMA}.{source_table}.{source_column}"
            )
        return
    if same_column:
        raise RuntimeError(
            "Migration 0059 found an unexpected foreign key for "
            f"{AYO_SCHEMA}.{source_table}.{source_column}"
        )
    op.create_foreign_key(
        name,
        source_table,
        target_table,
        [source_column],
        [target_column],
        source_schema=AYO_SCHEMA,
        referent_schema=AYO_SCHEMA,
    )


def _ensure_unique_constraint(*, name: str, table_name: str, column_name: str) -> None:
    constraints = sa.inspect(op.get_bind()).get_unique_constraints(
        table_name, schema=AYO_SCHEMA
    )
    named = [constraint for constraint in constraints if constraint["name"] == name]
    same_columns = [
        constraint
        for constraint in constraints
        if constraint["column_names"] == [column_name]
    ]
    if named:
        if len(named) != 1 or named[0]["column_names"] != [column_name]:
            raise RuntimeError(
                f"Migration 0059 found incompatible unique constraint {name}"
            )
        if len(same_columns) != 1:
            raise RuntimeError(
                "Migration 0059 found duplicate uniqueness constraints for "
                f"{AYO_SCHEMA}.{table_name}.{column_name}"
            )
        return
    if same_columns:
        raise RuntimeError(
            "Migration 0059 found an unexpected uniqueness constraint for "
            f"{AYO_SCHEMA}.{table_name}.{column_name}"
        )
    op.create_unique_constraint(
        name,
        table_name,
        [column_name],
        schema=AYO_SCHEMA,
    )


def _normalize_check_sql(value: str) -> str:
    return "".join(value.lower().split())


def _ensure_check_constraint(*, name: str, table_name: str, condition: str) -> None:
    constraints = sa.inspect(op.get_bind()).get_check_constraints(
        table_name, schema=AYO_SCHEMA
    )
    named = [constraint for constraint in constraints if constraint["name"] == name]
    expected_sql = _normalize_check_sql(condition)
    same_expression = [
        constraint
        for constraint in constraints
        if _normalize_check_sql(constraint["sqltext"]) == expected_sql
    ]
    if named:
        if len(named) != 1 or _normalize_check_sql(named[0]["sqltext"]) != expected_sql:
            raise RuntimeError(
                f"Migration 0059 found incompatible check constraint {name}"
            )
        if len(same_expression) != 1:
            raise RuntimeError(
                f"Migration 0059 found duplicate check constraint {name}"
            )
        return
    if same_expression:
        raise RuntimeError(
            "Migration 0059 found an unexpectedly named equivalent check "
            f"constraint on {AYO_SCHEMA}.{table_name}"
        )
    op.create_check_constraint(name, table_name, condition, schema=AYO_SCHEMA)


def upgrade() -> None:
    op.add_column(
        "post_trip_records",
        sa.Column("cash_evidence_state", sa.String(32)),
        schema="ayo",
    )
    _ensure_nullable_columns(
        "booking_confirmations",
        (
            sa.Column("fare_estimate_id", sa.UUID()),
            sa.Column("estimate_acceptance_id", sa.UUID()),
            sa.Column("pricing_lineage_hash", sa.String(64)),
        ),
    )
    _ensure_foreign_key(
        name="fk_booking_confirmation_fare_estimate",
        source_table="booking_confirmations",
        source_column="fare_estimate_id",
        target_table="fare_estimates",
        target_column="estimate_id",
    )
    _ensure_foreign_key(
        name="fk_booking_confirmation_estimate_acceptance",
        source_table="booking_confirmations",
        source_column="estimate_acceptance_id",
        target_table="fare_estimate_acceptances",
        target_column="acceptance_id",
    )
    _ensure_unique_constraint(
        name="uq_booking_confirmation_fare_estimate",
        table_name="booking_confirmations",
        column_name="fare_estimate_id",
    )
    _ensure_unique_constraint(
        name="uq_booking_confirmation_estimate_acceptance",
        table_name="booking_confirmations",
        column_name="estimate_acceptance_id",
    )

    _ensure_nullable_columns(
        "immediate_dispatch_handoffs",
        (
            sa.Column("fare_estimate_id", sa.UUID()),
            sa.Column("estimate_acceptance_id", sa.UUID()),
            sa.Column("pricing_policy_id", sa.UUID()),
            sa.Column("pricing_policy_version", sa.String(63)),
            sa.Column("pricing_lineage_hash", sa.String(64)),
        ),
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
        _ensure_foreign_key(
            name=constraint,
            source_table="immediate_dispatch_handoffs",
            source_column=column,
            target_table=table,
            target_column=target,
        )
    _ensure_check_constraint(
        name="handoff_pricing_lineage_complete",
        table_name="immediate_dispatch_handoffs",
        condition="(fare_estimate_id IS NULL AND estimate_acceptance_id IS NULL AND pricing_policy_id IS NULL AND pricing_policy_version IS NULL AND pricing_lineage_hash IS NULL) OR "
        "(fare_estimate_id IS NOT NULL AND estimate_acceptance_id IS NOT NULL AND pricing_policy_id IS NOT NULL AND pricing_policy_version IS NOT NULL AND pricing_lineage_hash IS NOT NULL)",
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
