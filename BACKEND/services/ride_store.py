"""Compatibility facade for callers not yet migrated to repository injection."""

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.repositories.contracts import RideRepository
from BACKEND.repositories.registry import get_ride_repository


def save_ride(ride: Ride, repository: RideRepository | None = None) -> Ride:
    return (repository or get_ride_repository()).save(ride)


def get_ride(ride_id: str, repository: RideRepository | None = None) -> Ride | None:
    return (repository or get_ride_repository()).get(ride_id)


def update_ride_status(
    ride_id: str,
    status: RideStatus,
    repository: RideRepository | None = None,
) -> Ride | None:
    return (repository or get_ride_repository()).update_status(ride_id, status)
