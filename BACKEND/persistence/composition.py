from sqlalchemy import Engine

from BACKEND.persistence.repositories import (
    PostgresLegacyWalletRepository,
    PostgresRideRepository,
)
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


class AyoPostgresUnitOfWork(SqlAlchemyUnitOfWork):
    """Current typed composition; future domains add repositories here."""

    @property
    def rides(self) -> PostgresRideRepository:
        return self.repository("rides", PostgresRideRepository)

    @property
    def legacy_wallets(self) -> PostgresLegacyWalletRepository:
        return self.repository("legacy_wallets", PostgresLegacyWalletRepository)


class PostgresRepositoryComposition:
    """Process-scoped factory for transaction-scoped repository sets."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "rides": PostgresRideRepository,
            "legacy_wallets": PostgresLegacyWalletRepository,
        }

    def unit_of_work(self) -> AyoPostgresUnitOfWork:
        return AyoPostgresUnitOfWork(self._engine, self._factories)
