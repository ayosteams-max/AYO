from BACKEND.repositories.contracts import LegacyWalletRepository, RideRepository
from BACKEND.repositories.memory import (
    InMemoryLegacyWalletRepository,
    InMemoryRideRepository,
)

_ride_repository = InMemoryRideRepository()
_wallet_repository = InMemoryLegacyWalletRepository()


def get_ride_repository() -> RideRepository:
    return _ride_repository


def get_wallet_repository() -> LegacyWalletRepository:
    return _wallet_repository


def reset_in_memory_repositories() -> None:
    """Reset development adapters. Intended for isolated automated tests only."""

    _ride_repository.clear()
    _wallet_repository.clear()
