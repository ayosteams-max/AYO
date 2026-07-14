from collections.abc import Mapping
from typing import Any, Protocol

from BACKEND.domain.rides import Ride, RideStatus


class RideRepository(Protocol):
    """Persistence boundary for ride aggregates."""

    def save(self, ride: Ride) -> Ride: ...

    def get(self, ride_id: str) -> Ride | None: ...

    def update_status(self, ride_id: str, status: RideStatus) -> Ride | None: ...


# This shape exists only to isolate the prototype wallet dictionary. It is not the
# target financial model and must not be migrated as authoritative value.
LegacyWalletRecord = dict[str, Any]


class LegacyWalletRepository(Protocol):
    """Temporary storage boundary for the existing, non-ledger wallet aggregate."""

    def get(self, driver_id: str) -> LegacyWalletRecord | None: ...

    def save(self, wallet: Mapping[str, Any]) -> LegacyWalletRecord: ...
