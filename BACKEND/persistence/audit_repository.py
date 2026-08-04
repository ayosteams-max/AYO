import logging
from collections.abc import Mapping
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, insert, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from BACKEND.audit.models import AuditEvent
from BACKEND.persistence.errors import AuditIdempotencyConflict
from BACKEND.persistence.logging import database_event
from BACKEND.persistence.tables import audit_events

_logger = logging.getLogger("ayo.persistence")


def _event_values(event: AuditEvent) -> dict[str, Any]:
    return event.model_dump(mode="python")


def _row_to_event(row: Mapping[Any, Any]) -> AuditEvent:
    return AuditEvent.model_validate(dict(row))


class PostgresAuditEventRepository:
    """Append/read-only PostgreSQL audit repository."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def append(self, event: AuditEvent) -> AuditEvent:
        started = perf_counter()
        outcome = "success"
        try:
            values = _event_values(event)
            if event.idempotency_key is None:
                row = (
                    self._connection.execute(
                        insert(audit_events).values(**values).returning(audit_events)
                    )
                    .mappings()
                    .one()
                )
                return _row_to_event(row)

            inserted_row = (
                self._connection.execute(
                    postgres_insert(audit_events)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=[
                            audit_events.c.source_module,
                            audit_events.c.action,
                            audit_events.c.idempotency_key,
                        ],
                        index_where=audit_events.c.idempotency_key.is_not(None),
                    )
                    .returning(audit_events)
                )
                .mappings()
                .one_or_none()
            )
            if inserted_row is not None:
                return _row_to_event(inserted_row)

            existing = (
                self._connection.execute(
                    select(audit_events).where(
                        audit_events.c.source_module == event.source_module,
                        audit_events.c.action == event.action,
                        audit_events.c.idempotency_key == event.idempotency_key,
                    )
                )
                .mappings()
                .one()
            )
            stored = _row_to_event(existing)
            comparable = {"event_id", "occurred_at", "recorded_at"}
            if stored.model_dump(exclude=comparable) != event.model_dump(
                exclude=comparable
            ):
                outcome = "conflict"
                raise AuditIdempotencyConflict(
                    "Audit idempotency key was reused for different event content"
                )
            return stored
        except Exception:
            if outcome == "success":
                outcome = "error"
            raise
        finally:
            database_event(
                _logger,
                event="audit.append",
                outcome=outcome,
                duration_ms=(perf_counter() - started) * 1_000,
            )

    def get(self, event_id: UUID) -> AuditEvent | None:
        row = (
            self._connection.execute(
                select(audit_events).where(audit_events.c.event_id == event_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _row_to_event(row)

    def find_by_correlation(
        self, correlation_id: UUID, *, limit: int = 100
    ) -> list[AuditEvent]:
        if not 1 <= limit <= 500:
            raise ValueError("Audit query limit must be between 1 and 500")
        rows = (
            self._connection.execute(
                select(audit_events)
                .where(audit_events.c.correlation_id == correlation_id)
                .order_by(audit_events.c.occurred_at, audit_events.c.event_id)
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [_row_to_event(row) for row in rows]


class StandaloneAuditWriter:
    """Bounded transaction for denied/failed events outside business state changes."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, event: AuditEvent) -> AuditEvent:
        if event.outcome.value not in {"denied", "failed"}:
            raise ValueError(
                "Standalone audit writes are limited to denied or failed outcomes"
            )
        with self._engine.begin() as connection:
            return PostgresAuditEventRepository(connection).append(event)
