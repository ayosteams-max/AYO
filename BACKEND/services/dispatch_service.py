from datetime import datetime, timedelta, timezone
from typing import Any

from BACKEND.models.driver import Driver

OFFER_TIMEOUT_SECONDS = 10
MAX_DRIVER_CANDIDATES = 5


def build_driver_queue(
    candidates: list[tuple[Driver, float]],
) -> list[dict[str, Any]]:
    """
    Build an ordered queue of suitable drivers.

    The candidates must already be sorted by:
    1. Pickup distance
    2. Eligibility
    3. Rating or fairness rules

    AYO keeps up to five backup drivers ready.
    """

    queue: list[dict[str, Any]] = []

    for driver, distance_km in candidates[:MAX_DRIVER_CANDIDATES]:
        queue.append(
            {
                "driver_id": driver.driver_id,
                "driver_name": driver.full_name,
                "distance_km": round(distance_km, 2),
                "offer_status": "QUEUED",
            }
        )

    return queue


def send_ride_offer(
    ride_id: str,
    driver: Driver,
) -> dict[str, Any]:
    """
    Send the current driver a ride offer lasting 10 seconds.

    Later this function will send:
    - Push notifications
    - Driver earnings
    - Pickup and destination details
    - Low-data notification payload
    """

    offered_at = datetime.now(timezone.utc)
    expires_at = offered_at + timedelta(seconds=OFFER_TIMEOUT_SECONDS)

    return {
        "ride_id": ride_id,
        "driver_id": driver.driver_id,
        "driver_name": driver.full_name,
        "offer_sent": True,
        "offer_timeout_seconds": OFFER_TIMEOUT_SECONDS,
        "offered_at": offered_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "status": "WAITING_FOR_DRIVER",
    }


def mark_offer_expired(
    ride_id: str,
    driver_id: str,
) -> dict[str, str]:
    """
    Mark an unanswered offer as expired.

    The next driver in the queue will then receive the ride.
    """

    return {
        "ride_id": ride_id,
        "driver_id": driver_id,
        "status": "OFFER_EXPIRED",
        "next_action": "OFFER_TO_NEXT_DRIVER",
    }
