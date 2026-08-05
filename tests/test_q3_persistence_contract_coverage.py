from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from BACKEND.persistence.errors import DuplicateEventError, IdempotencyConflictError
from BACKEND.persistence.kernel_models import (
    DomainEvent,
    IdempotencyRecord,
    canonical_request_hash,
)
from BACKEND.persistence.kernel_repository import (
    PostgresDomainEventRepository,
    PostgresIdempotencyRepository,
    PostgresTransactionalOutboxRepository,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _event() -> DomainEvent:
    return DomainEvent(
        event_type="test.contract.recorded",
        aggregate_type="test.contract",
        aggregate_id=str(uuid4()),
        source_module="test_contract",
        occurred_at=NOW,
        payload={"version": 1},
        correlation_id=uuid4(),
        request_id=uuid4(),
        idempotency_key="event-contract-0001",
    )


def _record(*, request: bytes = b"request") -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="test.contract",
        actor_reference=str(uuid4()),
        idempotency_key="idempotency-contract-0001",
        request_hash=canonical_request_hash(request),
        command_id=uuid4(),
        correlation_id=uuid4(),
        request_id=uuid4(),
        created_at=NOW,
    )


def _result(
    *,
    one_or_none: Any = None,
    one: Any = None,
    all_rows: list[Any] | None = None,
    scalars: list[Any] | None = None,
    rowcount: int = 0,
) -> Any:
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = one_or_none
    result.mappings.return_value.one.return_value = one
    result.mappings.return_value.all.return_value = all_rows or []
    result.scalars.return_value = scalars or []
    result.rowcount = rowcount
    return result


def _connection() -> tuple[Any, Connection]:
    raw = MagicMock()
    return raw, cast(Connection, raw)


def test_idempotency_reservation_replays_identical_request_and_rejects_conflict() -> (
    None
):
    record = _record()
    raw, connection = _connection()
    raw.execute.return_value = _result(one_or_none=record.model_dump(mode="python"))
    repository = PostgresIdempotencyRepository(connection)
    assert repository.reserve(record) == record

    raw.execute.side_effect = [
        _result(one_or_none=None),
        _result(one=record.model_dump(mode="python")),
    ]
    assert repository.reserve(record) == record

    conflicting = _record(request=b"different")
    raw.execute.side_effect = [
        _result(one_or_none=None),
        _result(one=record.model_dump(mode="python")),
    ]
    with pytest.raises(IdempotencyConflictError, match="different request"):
        repository.reserve(
            conflicting.model_copy(
                update={
                    "scope": record.scope,
                    "actor_reference": record.actor_reference,
                    "idempotency_key": record.idempotency_key,
                }
            )
        )


def test_idempotency_completion_validates_reference_and_replay_result() -> None:
    record = _record()
    raw, connection = _connection()
    repository = PostgresIdempotencyRepository(connection)
    with pytest.raises(ValueError, match="1 to 256"):
        repository.complete(record=record, response_reference="", completed_at=NOW)

    completed = record.model_copy(
        update={"response_reference": "resource/1", "completed_at": NOW}
    )
    raw.execute.return_value = _result(one_or_none=completed.model_dump(mode="python"))
    assert (
        repository.complete(
            record=record, response_reference="resource/1", completed_at=NOW
        )
        == completed
    )

    raw.execute.return_value = _result(one_or_none=None)
    repository.reserve = MagicMock(return_value=completed)  # type: ignore[method-assign]
    assert (
        repository.complete(
            record=record, response_reference="resource/1", completed_at=NOW
        )
        == completed
    )
    repository.reserve = MagicMock(return_value=record)  # type: ignore[method-assign]
    with pytest.raises(IdempotencyConflictError, match="completion conflicts"):
        repository.complete(
            record=record, response_reference="resource/1", completed_at=NOW
        )


def test_event_append_writes_event_and_outbox_and_maps_duplicate() -> None:
    event = _event()
    raw, connection = _connection()
    repository = PostgresDomainEventRepository(connection)
    assert repository.append(event) == event
    assert raw.execute.call_count == 2

    raw.execute.reset_mock()
    raw.execute.side_effect = IntegrityError("statement", {}, Exception("duplicate"))
    with pytest.raises(DuplicateEventError, match="already exists"):
        repository.append(event)

    raw.execute.side_effect = None
    raw.execute.return_value = _result(one_or_none=None)
    assert repository.get(event.event_id) is None
    raw.execute.return_value = _result(one_or_none=event.model_dump(mode="python"))
    assert repository.get(event.event_id) == event


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"worker_id": "bad worker"}, "identifier"),
        ({"worker_id": "worker-1", "limit": 0}, "claim limit"),
        ({"worker_id": "worker-1", "lease_seconds": 4}, "lease"),
    ],
)
def test_outbox_claim_validates_bounded_worker_contract(
    kwargs: dict[str, Any], message: str
) -> None:
    _, connection = _connection()
    repository = PostgresTransactionalOutboxRepository(connection)
    with pytest.raises(ValueError, match=message):
        repository.claim_ready(now=NOW, **kwargs)


def test_outbox_empty_claim_publish_and_failure_guards() -> None:
    raw, connection = _connection()
    repository = PostgresTransactionalOutboxRepository(connection)
    raw.execute.return_value = _result(scalars=[])
    assert repository.claim_ready(worker_id="worker-1", now=NOW) == []

    raw.execute.return_value = _result(rowcount=1)
    assert repository.mark_published(
        event_id=uuid4(), worker_id="worker-1", published_at=NOW
    )
    raw.execute.return_value = _result(rowcount=0)
    assert not repository.mark_published(
        event_id=uuid4(), worker_id="worker-1", published_at=NOW
    )

    for kwargs, message in (
        ({"error_code": ""}, "error code"),
        ({"error_code": "failed", "maximum_attempts": 0}, "Maximum attempts"),
        (
            {
                "error_code": "failed",
                "base_backoff_seconds": 10,
                "maximum_backoff_seconds": 5,
            },
            "backoff bounds",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            repository.mark_failed(
                event_id=uuid4(),
                worker_id="worker-1",
                failed_at=NOW,
                **kwargs,
            )
    raw.execute.return_value = _result(one_or_none=None)
    assert not repository.mark_failed(
        event_id=uuid4(),
        worker_id="worker-1",
        failed_at=NOW,
        error_code="failed",
    )
