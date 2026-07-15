from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, func, or_, select, update
from sqlalchemy.engine import RowMapping

from BACKEND.dispatch.outbox import APPROVED_OUTBOX_EVENTS, OutboxMessage
from BACKEND.persistence.tables import dispatch_outbox


def _message(row: Mapping[str, Any] | RowMapping) -> OutboxMessage:
    if row["event_type"] not in APPROVED_OUTBOX_EVENTS:
        raise ValueError("Outbox event type is not approved")
    payload = row["payload"]
    if not isinstance(payload, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in payload.items()
    ):
        raise ValueError("Outbox payload must contain bounded string fields")
    return OutboxMessage(
        message_id=row["message_id"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        event_type=row["event_type"],
        payload=payload,
        occurred_at=row["occurred_at"],
        attempt_count=row["attempt_count"],
    )


class PostgresOutboxRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def claim_ready(
        self,
        *,
        worker_id: str,
        now: datetime,
        limit: int,
        stale_after_seconds: int,
    ) -> list[OutboxMessage]:
        if not 1 <= len(worker_id) <= 64 or not worker_id.replace("-", "").isalnum():
            raise ValueError("Worker identifier is invalid")
        if not 1 <= limit <= 500:
            raise ValueError("Outbox claim limit must be between 1 and 500")
        if not 5 <= stale_after_seconds <= 3600:
            raise ValueError("Stale claim period must be between 5 and 3600 seconds")
        stale_before = now - timedelta(seconds=stale_after_seconds)
        ids = list(
            self._connection.execute(
                select(dispatch_outbox.c.message_id)
                .where(
                    dispatch_outbox.c.published_at.is_(None),
                    dispatch_outbox.c.dead_lettered_at.is_(None),
                    dispatch_outbox.c.available_at <= now,
                    or_(
                        dispatch_outbox.c.claimed_at.is_(None),
                        dispatch_outbox.c.claimed_at <= stale_before,
                    ),
                )
                .order_by(dispatch_outbox.c.available_at, dispatch_outbox.c.occurred_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not ids:
            return []
        rows = (
            self._connection.execute(
                update(dispatch_outbox)
                .where(dispatch_outbox.c.message_id.in_(ids))
                .values(claimed_at=now, claimed_by=worker_id)
                .returning(dispatch_outbox)
            )
            .mappings()
            .all()
        )
        return [_message(row) for row in rows]

    def mark_published(
        self, *, message_id: UUID, worker_id: str, published_at: datetime
    ) -> bool:
        changed = int(
            self._connection.execute(
                update(dispatch_outbox)
                .where(
                    dispatch_outbox.c.message_id == message_id,
                    dispatch_outbox.c.claimed_by == worker_id,
                    dispatch_outbox.c.published_at.is_(None),
                    dispatch_outbox.c.dead_lettered_at.is_(None),
                )
                .values(
                    published_at=published_at,
                    claimed_at=None,
                    claimed_by=None,
                    last_error_code=None,
                )
            ).rowcount
            or 0
        )
        return changed == 1

    def mark_failed(
        self,
        *,
        message_id: UUID,
        worker_id: str,
        failed_at: datetime,
        error_code: str,
        maximum_attempts: int,
        base_backoff_seconds: int,
        maximum_backoff_seconds: int,
    ) -> bool:
        if not error_code or len(error_code) > 63:
            raise ValueError("Outbox error code is invalid")
        if not 1 <= maximum_attempts <= 20:
            raise ValueError("Maximum attempts must be between 1 and 20")
        row = (
            self._connection.execute(
                select(dispatch_outbox)
                .where(
                    dispatch_outbox.c.message_id == message_id,
                    dispatch_outbox.c.claimed_by == worker_id,
                    dispatch_outbox.c.published_at.is_(None),
                    dispatch_outbox.c.dead_lettered_at.is_(None),
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return False
        attempts = int(row["attempt_count"]) + 1
        dead = attempts >= maximum_attempts
        backoff = min(
            maximum_backoff_seconds,
            base_backoff_seconds * (2 ** max(0, attempts - 1)),
        )
        self._connection.execute(
            update(dispatch_outbox)
            .where(dispatch_outbox.c.message_id == message_id)
            .values(
                attempt_count=attempts,
                last_error_code=error_code,
                claimed_at=None,
                claimed_by=None,
                available_at=failed_at + timedelta(seconds=backoff),
                dead_lettered_at=failed_at if dead else None,
            )
        )
        return dead

    def pending_lag_seconds(self, *, now: datetime) -> float:
        oldest = self._connection.execute(
            select(func.min(dispatch_outbox.c.available_at)).where(
                dispatch_outbox.c.published_at.is_(None),
                dispatch_outbox.c.dead_lettered_at.is_(None),
            )
        ).scalar_one()
        return 0.0 if oldest is None else max(0.0, (now - oldest).total_seconds())
