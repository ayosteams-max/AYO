"""Evolve Increment 4 into R1 Passenger Mobility Ride Request.

Revision ID: 20260723_0049
Revises: 20260723_0048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_0049"
down_revision: str | Sequence[str] | None = "20260723_0048"
branch_labels = None
depends_on = None
SCHEMA = "ayo"
TABLE = "canonical_ride_requests"


def _column_names() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(TABLE, schema=SCHEMA)
    }


def _constraint_names(kind: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if kind == "foreign":
        constraints = inspector.get_foreign_keys(TABLE, schema=SCHEMA)
    elif kind == "unique":
        constraints = inspector.get_unique_constraints(TABLE, schema=SCHEMA)
    else:
        constraints = inspector.get_check_constraints(TABLE, schema=SCHEMA)
    return {constraint["name"] for constraint in constraints if constraint["name"]}


def _add_column(column: sa.Column[object]) -> None:
    if column.name not in _column_names():
        op.add_column(TABLE, column, schema=SCHEMA)


def upgrade() -> None:
    op.alter_column(TABLE, "rider_identity_id", nullable=True, schema=SCHEMA)
    op.alter_column(TABLE, "service_type", nullable=True, schema=SCHEMA)
    op.alter_column(TABLE, "payment_intent", nullable=True, schema=SCHEMA)
    op.alter_column(TABLE, "pickup_id", nullable=True, schema=SCHEMA)
    op.alter_column(TABLE, "destination_id", nullable=True, schema=SCHEMA)
    op.alter_column(TABLE, "consent_policy_version", nullable=True, schema=SCHEMA)
    _add_column(
        sa.Column(
            "mobility_model_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        )
    )
    _add_column(sa.Column("requester_subject_id", postgresql.UUID(as_uuid=True)))
    _add_column(sa.Column("passenger_subject_id", postgresql.UUID(as_uuid=True)))
    _add_column(sa.Column("pickup_reference", sa.String(200)))
    _add_column(sa.Column("destination_reference", sa.String(200)))
    _add_column(
        sa.Column("stop_references", postgresql.JSONB(astext_type=sa.Text())),
    )
    _add_column(sa.Column("schedule_intent", sa.String(16)))
    _add_column(sa.Column("scheduled_for", sa.DateTime(timezone=True)))
    _add_column(sa.Column("passenger_count", sa.Integer()))
    _add_column(
        sa.Column("ride_preferences", postgresql.JSONB(astext_type=sa.Text())),
    )
    if "fk_ride_requests_requester_subject" not in _constraint_names("foreign"):
        op.create_foreign_key(
            "fk_ride_requests_requester_subject",
            TABLE,
            "canonical_subjects",
            ["requester_subject_id"],
            ["subject_id"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
        )
    if "fk_ride_requests_passenger_subject" not in _constraint_names("foreign"):
        op.create_foreign_key(
            "fk_ride_requests_passenger_subject",
            TABLE,
            "canonical_subjects",
            ["passenger_subject_id"],
            ["subject_id"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
        )
    if "uq_canonical_ride_requests_requester_subject_id" not in _constraint_names(
        "unique"
    ):
        op.create_unique_constraint(
            "uq_canonical_ride_requests_requester_subject_id",
            TABLE,
            ["requester_subject_id", "client_request_id"],
            schema=SCHEMA,
        )
    if (
        "ck_canonical_ride_requests_canonical_ride_request_model_version"
        not in _constraint_names("check")
    ):
        op.create_check_constraint(
            "ck_canonical_ride_requests_canonical_ride_request_model_version",
            TABLE,
            "mobility_model_version IN (1, 2)",
            schema=SCHEMA,
        )
    if (
        "ck_canonical_ride_requests_canonical_ride_request_model_shape"
        not in _constraint_names("check")
    ):
        op.create_check_constraint(
            "ck_canonical_ride_requests_canonical_ride_request_model_shape",
            TABLE,
            "(mobility_model_version = 1 AND rider_identity_id IS NOT NULL) OR "
            "(mobility_model_version = 2 AND requester_subject_id IS NOT NULL "
            "AND passenger_subject_id IS NOT NULL AND pickup_reference IS NOT NULL "
            "AND destination_reference IS NOT NULL AND schedule_intent IS NOT NULL "
            "AND passenger_count BETWEEN 1 AND 8)",
            schema=SCHEMA,
        )
    if (
        "ck_canonical_ride_requests_canonical_ride_request_schedule_intent"
        not in _constraint_names("check")
    ):
        op.create_check_constraint(
            "ck_canonical_ride_requests_canonical_ride_request_schedule_intent",
            TABLE,
            "schedule_intent IS NULL OR schedule_intent IN ('immediate','scheduled')",
            schema=SCHEMA,
        )


def downgrade() -> None:
    raise RuntimeError(
        "Forward-only migration: canonical Ride Request history must be preserved"
    )
