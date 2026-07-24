from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from BACKEND.persistence.errors import (
    DuplicateEventError,
    IdempotencyConflictError,
)
from BACKEND.persistence.kernel_models import (
    DomainEvent,
    IdempotencyRecord,
    OutboxEnvelope,
)
from BACKEND.persistence.tables import (
    persistence_domain_events,
    persistence_idempotency_records,
    persistence_outbox,
)


def _event_from_row(row: Mapping[str, Any] | RowMapping) -> DomainEvent:
    return DomainEvent.model_validate(
        {
            key: row[key]
            for key in (
                "event_id",
                "event_type",
                "aggregate_type",
                "aggregate_id",
                "source_module",
                "schema_version",
                "occurred_at",
                "payload",
                "correlation_id",
                "request_id",
                "command_id",
                "causation_id",
                "idempotency_key",
            )
        }
    )


class PostgresIdempotencyRepository:
    """Transaction-scoped command deduplication with payload conflict detection."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(self, record: IdempotencyRecord) -> IdempotencyRecord:
        values = record.model_dump(mode="python")
        inserted = (
            self._connection.execute(
                postgres_insert(persistence_idempotency_records)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        persistence_idempotency_records.c.scope,
                        persistence_idempotency_records.c.actor_reference,
                        persistence_idempotency_records.c.idempotency_key,
                    ]
                )
                .returning(persistence_idempotency_records)
            )
            .mappings()
            .one_or_none()
        )
        if inserted is not None:
            return IdempotencyRecord.model_validate(dict(inserted))
        existing = (
            self._connection.execute(
                select(persistence_idempotency_records).where(
                    persistence_idempotency_records.c.scope == record.scope,
                    persistence_idempotency_records.c.actor_reference
                    == record.actor_reference,
                    persistence_idempotency_records.c.idempotency_key
                    == record.idempotency_key,
                )
            )
            .mappings()
            .one()
        )
        stored = IdempotencyRecord.model_validate(dict(existing))
        if stored.request_hash != record.request_hash:
            raise IdempotencyConflictError(
                "Idempotency key was reused with a different request."
            )
        return stored

    def complete(
        self,
        *,
        record: IdempotencyRecord,
        response_reference: str,
        completed_at: datetime,
    ) -> IdempotencyRecord:
        if not 1 <= len(response_reference) <= 256:
            raise ValueError("Response reference must contain 1 to 256 characters")
        row = (
            self._connection.execute(
                update(persistence_idempotency_records)
                .where(
                    persistence_idempotency_records.c.scope == record.scope,
                    persistence_idempotency_records.c.actor_reference
                    == record.actor_reference,
                    persistence_idempotency_records.c.idempotency_key
                    == record.idempotency_key,
                    persistence_idempotency_records.c.request_hash
                    == record.request_hash,
                    persistence_idempotency_records.c.completed_at.is_(None),
                )
                .values(
                    response_reference=response_reference,
                    completed_at=completed_at,
                )
                .returning(persistence_idempotency_records)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            stored = self.reserve(record)
            if (
                stored.response_reference != response_reference
                or stored.completed_at is None
            ):
                raise IdempotencyConflictError(
                    "Command completion conflicts with the stored result."
                )
            return stored
        return IdempotencyRecord.model_validate(dict(row))


class PostgresDomainEventRepository:
    """Append-only event store whose outbox write shares the caller transaction."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def append(self, event: DomainEvent) -> DomainEvent:
        values = event.model_dump(mode="python")
        try:
            self._connection.execute(insert(persistence_domain_events).values(**values))
            self._connection.execute(
                insert(persistence_outbox).values(
                    event_id=event.event_id,
                    available_at=event.occurred_at,
                    attempt_count=0,
                )
            )
        except IntegrityError as error:
            raise DuplicateEventError(
                "Domain event identity or idempotency key already exists."
            ) from error
        return event

    def get(self, event_id: UUID) -> DomainEvent | None:
        row = (
            self._connection.execute(
                select(persistence_domain_events).where(
                    persistence_domain_events.c.event_id == event_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _event_from_row(row)


class PostgresTransactionalOutboxRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def claim_ready(
        self,
        *,
        worker_id: str,
        now: datetime,
        limit: int = 100,
        lease_seconds: int = 60,
    ) -> list[OutboxEnvelope]:
        if not 1 <= len(worker_id) <= 64 or not worker_id.replace("-", "").isalnum():
            raise ValueError("Worker identifier is invalid")
        if not 1 <= limit <= 500:
            raise ValueError("Outbox claim limit must be between 1 and 500")
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("Outbox lease must be between 5 and 3600 seconds")
        stale_before = now - timedelta(seconds=lease_seconds)
        event_ids = list(
            self._connection.execute(
                select(persistence_outbox.c.event_id)
                .where(
                    persistence_outbox.c.published_at.is_(None),
                    persistence_outbox.c.dead_lettered_at.is_(None),
                    persistence_outbox.c.available_at <= now,
                    or_(
                        persistence_outbox.c.claimed_at.is_(None),
                        persistence_outbox.c.claimed_at <= stale_before,
                    ),
                )
                .order_by(
                    persistence_outbox.c.available_at,
                    persistence_outbox.c.event_id,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not event_ids:
            return []
        claimed = list(
            self._connection.execute(
                update(persistence_outbox)
                .where(persistence_outbox.c.event_id.in_(event_ids))
                .values(claimed_at=now, claimed_by=worker_id)
                .returning(persistence_outbox)
            )
            .mappings()
            .all()
        )
        events = {
            row["event_id"]: _event_from_row(row)
            for row in self._connection.execute(
                select(persistence_domain_events).where(
                    persistence_domain_events.c.event_id.in_(event_ids)
                )
            )
            .mappings()
            .all()
        }
        position = {event_id: index for index, event_id in enumerate(event_ids)}
        claimed.sort(key=lambda row: position[row["event_id"]])
        return [
            OutboxEnvelope(
                event=events[row["event_id"]],
                attempt_count=row["attempt_count"],
                available_at=row["available_at"],
                claimed_by=row["claimed_by"],
            )
            for row in claimed
        ]

    def mark_published(
        self, *, event_id: UUID, worker_id: str, published_at: datetime
    ) -> bool:
        changed = self._connection.execute(
            update(persistence_outbox)
            .where(
                persistence_outbox.c.event_id == event_id,
                persistence_outbox.c.claimed_by == worker_id,
                persistence_outbox.c.published_at.is_(None),
                persistence_outbox.c.dead_lettered_at.is_(None),
            )
            .values(
                published_at=published_at,
                claimed_at=None,
                claimed_by=None,
                last_error_code=None,
            )
        ).rowcount
        return changed == 1

    def mark_failed(
        self,
        *,
        event_id: UUID,
        worker_id: str,
        failed_at: datetime,
        error_code: str,
        maximum_attempts: int = 10,
        base_backoff_seconds: int = 5,
        maximum_backoff_seconds: int = 3600,
    ) -> bool:
        if not 1 <= len(error_code) <= 63:
            raise ValueError("Outbox error code is invalid")
        if not 1 <= maximum_attempts <= 20:
            raise ValueError("Maximum attempts must be between 1 and 20")
        if not 1 <= base_backoff_seconds <= maximum_backoff_seconds <= 86_400:
            raise ValueError("Outbox backoff bounds are invalid")
        row = (
            self._connection.execute(
                select(persistence_outbox)
                .where(
                    persistence_outbox.c.event_id == event_id,
                    persistence_outbox.c.claimed_by == worker_id,
                    persistence_outbox.c.published_at.is_(None),
                    persistence_outbox.c.dead_lettered_at.is_(None),
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return False
        attempts = row["attempt_count"] + 1
        dead = attempts >= maximum_attempts
        backoff = min(
            maximum_backoff_seconds,
            base_backoff_seconds * (2 ** max(0, attempts - 1)),
        )
        self._connection.execute(
            update(persistence_outbox)
            .where(persistence_outbox.c.event_id == event_id)
            .values(
                attempt_count=attempts,
                available_at=failed_at + timedelta(seconds=backoff),
                claimed_at=None,
                claimed_by=None,
                last_error_code=error_code,
                dead_lettered_at=failed_at if dead else None,
            )
        )
        return dead
