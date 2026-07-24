from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.persistence.audit_repository import (
    PostgresAuditEventRepository,
    StandaloneAuditWriter,
)
from BACKEND.persistence.errors import AuditIdempotencyConflict
from BACKEND.persistence.tables import audit_events

pytestmark = [pytest.mark.integration, pytest.mark.audit]


def audit_event(**changes) -> AuditEvent:
    values = {
        "actor_type": ActorType.SYSTEM,
        "action": "ride.state.changed",
        "resource_type": "ride",
        "resource_id": "AUDIT-RIDE",
        "outcome": AuditOutcome.SUCCESS,
        "correlation_id": uuid4(),
        "source_module": "rides",
    }
    values.update(changes)
    return AuditEvent.model_validate(values)


def sample_ride() -> Ride:
    return Ride(
        ride_id="AUDIT-RIDE",
        rider_name="Synthetic Rider",
        pickup="Synthetic Pickup",
        destination="Synthetic Destination",
        ride_type="standard",
        status=RideStatus.WAITING_FOR_DRIVER,
    )


def test_append_get_and_correlation_retrieval(postgres_composition) -> None:
    correlation_id = uuid4()
    first = audit_event(correlation_id=correlation_id)
    second = audit_event(
        correlation_id=correlation_id,
        causation_id=first.event_id,
        outcome=AuditOutcome.CANCELLED,
        action="ride.cancelled",
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        stored_first = unit_of_work.audit_events.append(first)
        stored_second = unit_of_work.audit_events.append(second)

    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.audit_events.get(stored_first.event_id) == stored_first
        linked = unit_of_work.audit_events.find_by_correlation(correlation_id)
        assert {event.event_id for event in linked} == {
            stored_first.event_id,
            stored_second.event_id,
        }
        assert linked[1].causation_id == first.event_id
        with pytest.raises(ValueError, match="between 1 and 500"):
            unit_of_work.audit_events.find_by_correlation(correlation_id, limit=501)


def test_business_state_and_success_audit_commit_atomically(
    postgres_composition,
) -> None:
    event = audit_event(idempotency_key="ride-command-0001")
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.rides.save(sample_ride())
        unit_of_work.audit_events.append(event)

    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.rides.get("AUDIT-RIDE") is not None
        assert unit_of_work.audit_events.get(event.event_id) is not None


def test_rollback_removes_business_and_success_audit_writes(
    postgres_composition,
) -> None:
    event = audit_event()
    with (
        pytest.raises(RuntimeError, match="force rollback"),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        unit_of_work.rides.save(sample_ride())
        unit_of_work.audit_events.append(event)
        raise RuntimeError("force rollback")

    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.rides.get("AUDIT-RIDE") is None
        assert unit_of_work.audit_events.get(event.event_id) is None


@pytest.mark.parametrize("outcome", [AuditOutcome.DENIED, AuditOutcome.FAILED])
def test_denied_and_failed_events_use_bounded_standalone_transaction(
    postgres_engine, postgres_composition, outcome
) -> None:
    event = audit_event(
        outcome=outcome,
        reason="policy_denied" if outcome is AuditOutcome.DENIED else "state_conflict",
    )

    stored = StandaloneAuditWriter(postgres_engine).append(event)

    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.audit_events.get(stored.event_id) == stored
    with pytest.raises(ValueError, match="denied or failed"):
        StandaloneAuditWriter(postgres_engine).append(audit_event())


def test_idempotent_retry_returns_one_record_and_conflicting_reuse_fails(
    postgres_composition, postgres_engine
) -> None:
    correlation_id = uuid4()
    first = audit_event(
        correlation_id=correlation_id,
        idempotency_key="ride-command-0002",
    )
    retry = audit_event(
        correlation_id=correlation_id,
        idempotency_key="ride-command-0002",
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        stored = unit_of_work.audit_events.append(first)
    with postgres_composition.unit_of_work() as unit_of_work:
        retried = unit_of_work.audit_events.append(retry)
    assert retried.event_id == stored.event_id

    conflicting = audit_event(
        correlation_id=correlation_id,
        idempotency_key="ride-command-0002",
        outcome=AuditOutcome.FAILED,
    )
    with (
        pytest.raises(AuditIdempotencyConflict),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        unit_of_work.audit_events.append(conflicting)

    with postgres_engine.connect() as connection:
        count = connection.execute(
            select(func.count()).select_from(audit_events)
        ).scalar_one()
    assert count == 1


def test_concurrent_appends_are_not_globally_serialized(
    postgres_composition, postgres_engine
) -> None:
    correlation_id = uuid4()

    def append(index: int):
        event = audit_event(
            correlation_id=correlation_id,
            resource_id=f"RIDE-{index}",
        )
        with postgres_composition.unit_of_work() as unit_of_work:
            return unit_of_work.audit_events.append(event).event_id

    with ThreadPoolExecutor(max_workers=3) as executor:
        event_ids = set(executor.map(append, range(20)))

    assert len(event_ids) == 20
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            == 20
        )


def test_repository_surface_is_append_and_read_only() -> None:
    assert not hasattr(PostgresAuditEventRepository, "update")
    assert not hasattr(PostgresAuditEventRepository, "delete")
