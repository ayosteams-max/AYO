from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RideStatus(str, Enum):
    REQUESTED = "REQUESTED"
    SEARCHING_FOR_DRIVER = "SEARCHING_FOR_DRIVER"
    WAITING_FOR_DRIVER = "WAITING_FOR_DRIVER"
    DRIVER_ACCEPTED = "DRIVER_ACCEPTED"
    DRIVER_ON_THE_WAY = "DRIVER_ON_THE_WAY"
    DRIVER_ARRIVED = "DRIVER_ARRIVED"
    TRIP_STARTED = "TRIP_STARTED"
    TRIP_COMPLETED = "TRIP_COMPLETED"
    DRIVER_DECLINED = "DRIVER_DECLINED"
    RIDER_CANCELLED = "RIDER_CANCELLED"
    DRIVER_CANCELLED = "DRIVER_CANCELLED"


@dataclass(slots=True)
class Ride:
    """Storage-neutral representation of the current ride aggregate.

    Dispatch internals remain on the aggregate for behavior compatibility. They
    must not become part of the future public API contract.
    """

    ride_id: str
    rider_name: str
    pickup: str
    destination: str
    ride_type: str
    status: RideStatus
    driver_id: str | None = None
    driver_name: str | None = None
    driver_distance_km: float | None = None
    driver_queue: list[dict[str, Any]] = field(default_factory=list)
    current_offer_index: int | None = None
    current_offer: dict[str, Any] | None = None
    gross_fare: float | None = None
    payment_method: str | None = None
    tip: float | None = None
    bonus: float | None = None

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return the existing API shape during the compatibility migration."""

        result: dict[str, Any] = {
            "ride_id": self.ride_id,
            "rider_name": self.rider_name,
            "pickup": self.pickup,
            "destination": self.destination,
            "ride_type": self.ride_type,
            "driver_id": self.driver_id,
            "driver_name": self.driver_name,
            "driver_distance_km": self.driver_distance_km,
            "status": self.status.value,
            "driver_queue": deepcopy(self.driver_queue),
            "current_offer_index": self.current_offer_index,
            "current_offer": deepcopy(self.current_offer),
        }
        optional_values = {
            "gross_fare": self.gross_fare,
            "payment_method": self.payment_method,
            "tip": self.tip,
            "bonus": self.bonus,
        }
        result.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        return result
