"""Add scheduled ride and smart pre-dispatch authority.

Revision ID: 20260716_0011
Revises: 20260716_0010
"""

from collections.abc import Sequence

from alembic import op

from BACKEND.persistence.tables import metadata

revision: str = "20260716_0011"
down_revision: str | Sequence[str] | None = "20260716_0010"
branch_labels = None
depends_on = None

TABLES = (
    "ride_reservations",
    "reservation_participants",
    "reservation_consents",
    "reservation_state_history",
    "reservation_planning_cycles",
    "reservation_driver_commitments",
    "reservation_soft_plans",
    "reservation_attempts",
    "reservation_checkpoints",
    "reservation_flight_context",
    "reservation_idempotency_records",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    bind = op.get_bind()
    for name in TABLES:
        metadata.tables[f"ayo.{name}"].create(bind, checkfirst=False)
    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON ayo.ride_reservations TO ayo_runtime;
        GRANT SELECT, INSERT, UPDATE ON ayo.reservation_participants,
          ayo.reservation_planning_cycles, ayo.reservation_driver_commitments,
          ayo.reservation_soft_plans, ayo.reservation_checkpoints,
          ayo.reservation_flight_context TO ayo_runtime;
        GRANT SELECT, INSERT ON ayo.reservation_consents,
          ayo.reservation_state_history, ayo.reservation_attempts,
          ayo.reservation_idempotency_records TO ayo_runtime;
        END IF; END $$"""
    )


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLES):
        metadata.tables[f"ayo.{name}"].drop(bind, checkfirst=False)
    # btree_gist is intentionally retained: extensions can be shared by other schemas.
