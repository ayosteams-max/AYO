from datetime import UTC, datetime
from typing import Annotated, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

APPROVED_OUTBOX_EVENTS = frozenset(
    {
        "dispatch.ride.requested",
        "dispatch.driver_offer.created",
        "dispatch.driver_offer.expired",
        "dispatch.driver_offer.declined",
        "dispatch.driver.assigned",
        "dispatch.ride.no_driver_available",
    }
)


class OutboxMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: Annotated[str, Field(min_length=3, max_length=63)]
    payload: dict[str, str]
    occurred_at: datetime
    attempt_count: Annotated[int, Field(ge=0)]

    @field_validator("occurred_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Outbox time must be timezone-aware")
        return value.astimezone(UTC)


class OutboxPublisher(Protocol):
    def publish(self, message: OutboxMessage) -> None:
        """Deliver using message_id as the provider idempotency key."""


class LocalIdempotentPublisher:
    """Controlled local/test publisher; no network or external provider."""

    def __init__(self) -> None:
        self.delivered: dict[UUID, OutboxMessage] = {}

    def publish(self, message: OutboxMessage) -> None:
        existing = self.delivered.get(message.message_id)
        if existing is not None and existing != message:
            raise RuntimeError("Message identifier content conflict")
        self.delivered[message.message_id] = message


class OutboxRepository(Protocol):
    def claim_ready(
        self,
        *,
        worker_id: str,
        now: datetime,
        limit: int,
        stale_after_seconds: int,
    ) -> list[OutboxMessage]: ...

    def mark_published(
        self, *, message_id: UUID, worker_id: str, published_at: datetime
    ) -> bool: ...

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
    ) -> bool: ...

    def pending_lag_seconds(self, *, now: datetime) -> float: ...
