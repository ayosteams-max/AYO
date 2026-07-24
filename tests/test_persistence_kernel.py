from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert

from BACKEND.persistence.concurrency import compare_and_swap
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.kernel_models import DomainEvent, canonical_request_hash
from BACKEND.persistence.trace import (
    TraceContext,
    bind_trace_context,
    current_trace_context,
)


def test_trace_context_propagates_and_restores_nested_context() -> None:
    root = TraceContext.new()
    command_id = uuid4()
    with bind_trace_context(root):
        assert current_trace_context() == root
        child = root.child(command_id=command_id)
        with bind_trace_context(child):
            assert current_trace_context().command_id == command_id
            assert current_trace_context().correlation_id == root.correlation_id
        assert current_trace_context() == root
    with pytest.raises(RuntimeError, match="not bound"):
        current_trace_context()


def test_domain_event_contract_is_bounded_and_hash_is_deterministic() -> None:
    trace = TraceContext.new()
    event = DomainEvent(
        event_type="example.changed",
        aggregate_type="example",
        aggregate_id="example-1",
        source_module="example",
        payload={"status": "ready", "version": 2},
        correlation_id=trace.correlation_id,
        request_id=trace.request_id,
    )
    assert event.payload["status"] == "ready"
    assert canonical_request_hash(b"stable") == canonical_request_hash(b"stable")
    with pytest.raises(ValidationError, match="32 fields"):
        DomainEvent(
            event_type="example.changed",
            aggregate_type="example",
            aggregate_id="example-1",
            source_module="example",
            payload={f"field_{i}": i for i in range(33)},
            correlation_id=trace.correlation_id,
            request_id=trace.request_id,
        )


def test_compare_and_swap_enforces_authoritative_version() -> None:
    metadata = MetaData()
    records = Table(
        "versioned_records",
        metadata,
        Column("record_id", String, primary_key=True),
        Column("value", String, nullable=False),
        Column("version", Integer, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(records).values(record_id="record-1", value="before", version=1)
        )
        assert (
            compare_and_swap(
                connection,
                table=records,
                identity=records.c.record_id == "record-1",
                expected_version=1,
                values={"value": "after"},
            )
            == 2
        )
        with pytest.raises(OptimisticConcurrencyError):
            compare_and_swap(
                connection,
                table=records,
                identity=records.c.record_id == "record-1",
                expected_version=1,
                values={"value": "stale"},
            )
    engine.dispose()
