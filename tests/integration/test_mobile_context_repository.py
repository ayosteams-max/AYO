from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update

from BACKEND.persistence.courier_pickup_repository import (
    PostgresCourierPickupRepository,
)
from BACKEND.persistence.tables import (
    commerce_courier_dispatch_requests,
    commerce_courier_pickup_events,
    commerce_courier_pickup_evidence,
    commerce_courier_pickup_idempotency,
    commerce_courier_pickups,
    commerce_order_outbox,
    courier_dispatch_assignments,
)
from tests.integration.test_courier_pickup_idempotency import (
    ACTOR,
    ASSIGNMENT,
    DISPATCH,
    PICKUP,
    _cleanup_command_state,
    _seed_command_state,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def context_state(postgres_engine):
    _cleanup_command_state(postgres_engine)
    _seed_command_state(postgres_engine)
    try:
        yield
    finally:
        _cleanup_command_state(postgres_engine)


def _effect_counts(connection) -> tuple[int, ...]:
    return tuple(
        connection.execute(select(func.count()).select_from(table)).scalar_one()
        for table in (
            commerce_courier_pickup_events,
            commerce_courier_pickup_evidence,
            commerce_courier_pickup_idempotency,
            commerce_order_outbox,
        )
    )


@pytest.mark.usefixtures("context_state")
def test_current_courier_lookup_is_exact_bounded_and_side_effect_free(
    postgres_engine,
) -> None:
    with postgres_engine.begin() as connection:
        repository = PostgresCourierPickupRepository(connection)
        before = _effect_counts(connection)
        first = repository.current_for_courier(ACTOR)
        second = repository.current_for_courier(ACTOR)
        after = _effect_counts(connection)
        assert [item.pickup_id for item in first] == [PICKUP]
        assert first == second
        assert before == after
        assert repository.current_for_courier(uuid4()) == ()


@pytest.mark.usefixtures("context_state")
@pytest.mark.parametrize("failure", ["released", "cancelled", "stale", "replaced"])
def test_inactive_or_stale_assignment_is_omitted(postgres_engine, failure) -> None:
    with postgres_engine.begin() as connection:
        if failure in {"released", "cancelled"}:
            connection.execute(
                update(courier_dispatch_assignments)
                .where(courier_dispatch_assignments.c.assignment_id == ASSIGNMENT)
                .values(state=f"{failure}_before_pickup")
            )
        elif failure == "stale":
            connection.execute(
                update(commerce_courier_pickups)
                .where(commerce_courier_pickups.c.pickup_id == PICKUP)
                .values(assignment_version=2)
            )
        else:
            connection.execute(
                update(commerce_courier_dispatch_requests)
                .where(commerce_courier_dispatch_requests.c.dispatch_id == DISPATCH)
                .values(active_assignment_id=None)
            )
        assert (
            PostgresCourierPickupRepository(connection).current_for_courier(ACTOR) == ()
        )


@pytest.mark.usefixtures("context_state")
def test_current_courier_lookup_uses_the_partial_index(postgres_engine) -> None:
    with postgres_engine.begin() as connection:
        index = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='ayo' "
                "AND indexname='ix_courier_pickup_current_courier'"
            )
        ).scalar_one()
        assert "assigned_courier_identity_id" in index
        assert "updated_at DESC" in index
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                text(
                    "EXPLAIN SELECT pickup_id "
                    "FROM ayo.commerce_courier_pickups "
                    "WHERE assigned_courier_identity_id = :courier "
                    "AND state IN ('courier_assigned', 'travelling_to_merchant', "
                    "'arrived_at_merchant', 'waiting_for_pickup') "
                    "ORDER BY updated_at DESC, pickup_id LIMIT 2"
                ),
                {"courier": ACTOR},
            )
        )
        assert "ix_courier_pickup_current_courier" in plan
