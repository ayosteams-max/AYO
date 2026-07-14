from sqlalchemy import Engine

from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.rate_limit_repository import PostgresTokenBucketRateLimiter
from BACKEND.persistence.repositories import (
    PostgresLegacyWalletRepository,
    PostgresRideRepository,
)
from BACKEND.persistence.session_repository import PostgresSessionRepository
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


class AyoPostgresUnitOfWork(SqlAlchemyUnitOfWork):
    """Current typed composition; future domains add repositories here."""

    @property
    def rides(self) -> PostgresRideRepository:
        return self.repository("rides", PostgresRideRepository)

    @property
    def legacy_wallets(self) -> PostgresLegacyWalletRepository:
        return self.repository("legacy_wallets", PostgresLegacyWalletRepository)

    @property
    def audit_events(self) -> PostgresAuditEventRepository:
        return self.repository("audit_events", PostgresAuditEventRepository)

    @property
    def sessions(self) -> PostgresSessionRepository:
        return self.repository("sessions", PostgresSessionRepository)

    @property
    def rate_limits(self) -> PostgresTokenBucketRateLimiter:
        return self.repository("rate_limits", PostgresTokenBucketRateLimiter)


class PostgresRepositoryComposition:
    """Process-scoped factory for transaction-scoped repository sets."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "rides": PostgresRideRepository,
            "legacy_wallets": PostgresLegacyWalletRepository,
            "audit_events": PostgresAuditEventRepository,
            "sessions": PostgresSessionRepository,
            "rate_limits": PostgresTokenBucketRateLimiter,
        }

    def unit_of_work(self) -> AyoPostgresUnitOfWork:
        return AyoPostgresUnitOfWork(self._engine, self._factories)
