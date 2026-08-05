from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.persistence.errors import (
    DuplicateEventError,
    IdempotencyConflictError,
)
from BACKEND.persistence.kernel_models import (
    DomainEvent,
    IdempotencyRecord,
    canonical_request_hash,
)
from BACKEND.persistence.tables import (
    audit_events,
    persistence_domain_events,
    persistence_idempotency_records,
    persistence_outbox,
)
from BACKEND.persistence.trace import TraceContext

pytestmark = [pytest.mark.integration, pytest.mark.persistence_kernel]


def command_record(trace: TraceContext, *, body: bytes = b'{"value":1}'):
    return IdempotencyRecord(
        scope="example.create",
        actor_reference="actor-1",
        idempotency_key="example-command-0001",
        request_hash=canonical_request_hash(body),
        command_id=trace.command_id or uuid4(),
        correlation_id=trace.correlation_id,
        request_id=trace.request_id,
        created_at=datetime.now(UTC),
    )


def domain_event(trace: TraceContext, *, event_id=None, key="example-event-0001"):
    return DomainEvent(
        event_id=event_id or uuid4(),
        event_type="example.created",
        aggregate_type="example",
        aggregate_id="example-1",
        source_module="example",
        payload={"state": "created"},
        correlation_id=trace.correlation_id,
        request_id=trace.request_id,
        command_id=trace.command_id,
        idempotency_key=key,
    )


def success_audit(trace: TraceContext) -> AuditEvent:
    return AuditEvent(
        actor_type=ActorType.SYSTEM,
        action="example.created",
        resource_type="example",
        resource_id="example-1",
        outcome=AuditOutcome.SUCCESS,
        correlation_id=trace.correlation_id,
        request_id=trace.request_id,
        source_module="persistence_test",
        idempotency_key="example-audit-0001",
    )


def test_command_event_outbox_and_audit_commit_atomically(
    persistence_kernel, postgres_engine
) -> None:
    trace = TraceContext.new().child(command_id=uuid4())
    record = command_record(trace)
    event = domain_event(trace)
    audit = success_audit(trace)
    with persistence_kernel.unit_of_work() as unit_of_work:
        reserved = unit_of_work.idempotency.reserve(record)
        unit_of_work.events.append(event)
        unit_of_work.audit.append(audit)
        completed = unit_of_work.idempotency.complete(
            record=reserved,
            response_reference="example/example-1",
            completed_at=datetime.now(UTC),
        )
        assert completed.completed_at is not None

    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_domain_events)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_outbox)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_idempotency_records)
            ).scalar_one()
            == 1
        )


def test_failure_rolls_back_command_event_outbox_and_audit(
    persistence_kernel, postgres_engine
) -> None:
    trace = TraceContext.new().child(command_id=uuid4())
    with (
        pytest.raises(RuntimeError, match="rollback"),
        persistence_kernel.unit_of_work() as unit_of_work,
    ):
        unit_of_work.idempotency.reserve(command_record(trace))
        unit_of_work.events.append(domain_event(trace))
        unit_of_work.audit.append(success_audit(trace))
        raise RuntimeError("rollback")
    with postgres_engine.connect() as connection:
        for table in (
            audit_events,
            persistence_domain_events,
            persistence_outbox,
            persistence_idempotency_records,
        ):
            assert (
                connection.execute(select(func.count()).select_from(table)).scalar_one()
                == 0
            )


def test_idempotency_replay_and_changed_payload_conflict(persistence_kernel) -> None:
    trace = TraceContext.new().child(command_id=uuid4())
    original = command_record(trace)
    with persistence_kernel.unit_of_work() as unit_of_work:
        first = unit_of_work.idempotency.reserve(original)
        completed = unit_of_work.idempotency.complete(
            record=first,
            response_reference="example/example-1",
            completed_at=datetime.now(UTC),
        )
    with persistence_kernel.unit_of_work() as unit_of_work:
        replay = unit_of_work.idempotency.reserve(original)
    assert replay.command_id == completed.command_id
    assert replay.response_reference == "example/example-1"
    with (
        pytest.raises(IdempotencyConflictError),
        persistence_kernel.unit_of_work() as unit_of_work,
    ):
        unit_of_work.idempotency.reserve(command_record(trace, body=b"changed"))


def test_duplicate_event_is_rejected_and_original_is_immutable(
    persistence_kernel, postgres_engine
) -> None:
    trace = TraceContext.new().child(command_id=uuid4())
    first = domain_event(trace)
    with persistence_kernel.unit_of_work() as unit_of_work:
        unit_of_work.events.append(first)
    with (
        pytest.raises(DuplicateEventError),
        persistence_kernel.unit_of_work() as unit_of_work,
    ):
        unit_of_work.events.append(domain_event(trace))
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_domain_events)
            ).scalar_one()
            == 1
        )


def test_concurrent_workers_claim_one_event_and_replay_is_safe(
    persistence_kernel, postgres_engine
) -> None:
    now = datetime.now(UTC)
    event = domain_event(TraceContext.new())
    with persistence_kernel.unit_of_work() as unit_of_work:
        unit_of_work.events.append(event)

    def claim(worker_id: str):
        with persistence_kernel.unit_of_work() as unit_of_work:
            return unit_of_work.outbox.claim_ready(
                worker_id=worker_id, now=now + timedelta(seconds=1)
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-1", "worker-2")))
    assert sum(len(claimed) for claimed in claims) == 1
    winner = next(items[0] for items in claims if items)
    assert winner.event.event_id == event.event_id
    with persistence_kernel.unit_of_work() as unit_of_work:
        assert unit_of_work.outbox.mark_published(
            event_id=event.event_id,
            worker_id=winner.claimed_by or "",
            published_at=now + timedelta(seconds=2),
        )
    with persistence_kernel.unit_of_work() as unit_of_work:
        assert (
            unit_of_work.outbox.claim_ready(
                worker_id="worker-3", now=now + timedelta(seconds=120)
            )
            == []
        )
    with postgres_engine.connect() as connection:
        stored = (
            connection.execute(
                select(persistence_outbox).where(
                    persistence_outbox.c.event_id == event.event_id
                )
            )
            .mappings()
            .one()
        )
    assert stored["published_at"] is not None


def test_failed_delivery_reappears_after_backoff_and_survives_restart(
    persistence_kernel,
) -> None:
    now = datetime.now(UTC)
    event = domain_event(TraceContext.new())
    with persistence_kernel.unit_of_work() as unit_of_work:
        unit_of_work.events.append(event)
    delivery_time = now + timedelta(seconds=1)
    with persistence_kernel.unit_of_work() as unit_of_work:
        claimed = unit_of_work.outbox.claim_ready(
            worker_id="worker-1", now=delivery_time
        )
        assert len(claimed) == 1
        assert not unit_of_work.outbox.mark_failed(
            event_id=event.event_id,
            worker_id="worker-1",
            failed_at=delivery_time,
            error_code="provider_unavailable",
        )
    with persistence_kernel.unit_of_work() as unit_of_work:
        assert (
            unit_of_work.outbox.claim_ready(
                worker_id="worker-2", now=delivery_time + timedelta(seconds=4)
            )
            == []
        )
    with persistence_kernel.unit_of_work() as unit_of_work:
        replay = unit_of_work.outbox.claim_ready(
            worker_id="worker-2", now=delivery_time + timedelta(seconds=5)
        )
    assert replay[0].event.event_id == event.event_id
    assert replay[0].attempt_count == 1
