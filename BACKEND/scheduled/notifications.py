from typing import Protocol
from uuid import UUID

from BACKEND.scheduled.integration_models import NotificationMessage


class ReservationNotificationPublisher(Protocol):
    def publish(self, message: NotificationMessage) -> None: ...


class LocalReservationNotificationPublisher:
    """Idempotent local/test adapter; never contacts an external provider."""

    def __init__(self) -> None:
        self.delivered: dict[UUID, NotificationMessage] = {}

    def publish(self, message: NotificationMessage) -> None:
        existing = self.delivered.get(message.event_id)
        if existing is not None and existing != message:
            raise RuntimeError("Notification event identifier conflict")
        self.delivered[message.event_id] = message
