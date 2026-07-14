from collections.abc import Mapping
from copy import deepcopy
from threading import RLock
from typing import Any

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.repositories.contracts import LegacyWalletRecord


class InMemoryRideRepository:
    """Thread-safe development adapter; never a production source of truth."""

    def __init__(self) -> None:
        self._rides: dict[str, Ride] = {}
        self._lock = RLock()

    def save(self, ride: Ride) -> Ride:
        with self._lock:
            self._rides[ride.ride_id] = deepcopy(ride)
            return deepcopy(ride)

    def get(self, ride_id: str) -> Ride | None:
        with self._lock:
            ride = self._rides.get(ride_id)
            return deepcopy(ride) if ride is not None else None

    def update_status(self, ride_id: str, status: RideStatus) -> Ride | None:
        with self._lock:
            ride = self._rides.get(ride_id)
            if ride is None:
                return None
            ride.status = status
            return deepcopy(ride)

    def clear(self) -> None:
        with self._lock:
            self._rides.clear()


class InMemoryLegacyWalletRepository:
    """Thread-safe compatibility adapter for untrusted prototype wallet state."""

    def __init__(self) -> None:
        self._wallets: dict[str, LegacyWalletRecord] = {}
        self._lock = RLock()

    def get(self, driver_id: str) -> LegacyWalletRecord | None:
        with self._lock:
            wallet = self._wallets.get(driver_id)
            return deepcopy(wallet) if wallet is not None else None

    def save(self, wallet: Mapping[str, Any]) -> LegacyWalletRecord:
        stored = deepcopy(dict(wallet))
        with self._lock:
            self._wallets[stored["driver_id"]] = stored
            return deepcopy(stored)

    def clear(self) -> None:
        with self._lock:
            self._wallets.clear()
