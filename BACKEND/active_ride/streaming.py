from typing import Protocol
from uuid import UUID

from BACKEND.active_ride.models import RideEvent


class FutureRideEventStream(Protocol):
    """Provider-neutral future foreground stream; polling remains authoritative fallback."""

    def publish(self, event: RideEvent) -> None: ...

    def disconnect_ride(self, ride_id: UUID) -> None: ...


class DisabledRideEventStream:
    def publish(self, event: RideEvent) -> None:
        del event

    def disconnect_ride(self, ride_id: UUID) -> None:
        del ride_id
