from sqlalchemy import Engine

from BACKEND.persistence.active_ride_repository import PostgresActiveRideRepository
from BACKEND.persistence.arrival_waiting_repository import (
    PostgresArrivalWaitingRepository,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.authorization_repository import (
    PostgresAuthorizationRepository,
)
from BACKEND.persistence.dispatch_repository import (
    DriverCandidateGateway,
    NoDriverCandidateGateway,
    PostgresDispatchRepository,
)
from BACKEND.persistence.identity_repository import (
    PostgresAuthenticationChallengeRepository,
    PostgresIdentityRepository,
    PostgresRefreshTokenRepository,
)
from BACKEND.persistence.outbox_repository import PostgresOutboxRepository
from BACKEND.persistence.rate_limit_repository import PostgresTokenBucketRateLimiter
from BACKEND.persistence.repositories import (
    PostgresLegacyWalletRepository,
    PostgresRideRepository,
)
from BACKEND.persistence.scheduled_repository import PostgresScheduledRepository
from BACKEND.persistence.session_repository import PostgresSessionRepository
from BACKEND.persistence.support_repository import PostgresSupportRepository
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


class AyoPostgresUnitOfWork(SqlAlchemyUnitOfWork):
    """Current typed composition; future domains add repositories here."""

    def __enter__(self) -> "AyoPostgresUnitOfWork":
        super().__enter__()
        return self

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

    @property
    def identities(self) -> PostgresIdentityRepository:
        return self.repository("identities", PostgresIdentityRepository)

    @property
    def authentication_challenges(self) -> PostgresAuthenticationChallengeRepository:
        return self.repository(
            "authentication_challenges", PostgresAuthenticationChallengeRepository
        )

    @property
    def refresh_tokens(self) -> PostgresRefreshTokenRepository:
        return self.repository("refresh_tokens", PostgresRefreshTokenRepository)

    @property
    def authorization(self) -> PostgresAuthorizationRepository:
        return self.repository("authorization", PostgresAuthorizationRepository)

    @property
    def support(self) -> PostgresSupportRepository:
        return self.repository("support", PostgresSupportRepository)

    @property
    def dispatch(self) -> PostgresDispatchRepository:
        return self.repository("dispatch", PostgresDispatchRepository)

    @property
    def outbox(self) -> PostgresOutboxRepository:
        return self.repository("outbox", PostgresOutboxRepository)

    @property
    def scheduled(self) -> PostgresScheduledRepository:
        return self.repository("scheduled", PostgresScheduledRepository)

    @property
    def active_rides(self) -> PostgresActiveRideRepository:
        return self.repository("active_rides", PostgresActiveRideRepository)

    @property
    def arrival_waiting(self) -> PostgresArrivalWaitingRepository:
        return self.repository("arrival_waiting", PostgresArrivalWaitingRepository)


class PostgresRepositoryComposition:
    """Process-scoped factory for transaction-scoped repository sets."""

    def __init__(
        self,
        engine: Engine,
        *,
        dispatch_candidates: DriverCandidateGateway | None = None,
    ) -> None:
        self._engine = engine
        candidate_gateway = dispatch_candidates or NoDriverCandidateGateway()
        self._factories = {
            "rides": PostgresRideRepository,
            "legacy_wallets": PostgresLegacyWalletRepository,
            "audit_events": PostgresAuditEventRepository,
            "sessions": PostgresSessionRepository,
            "rate_limits": PostgresTokenBucketRateLimiter,
            "identities": PostgresIdentityRepository,
            "authentication_challenges": PostgresAuthenticationChallengeRepository,
            "refresh_tokens": PostgresRefreshTokenRepository,
            "authorization": PostgresAuthorizationRepository,
            "support": PostgresSupportRepository,
            "dispatch": lambda connection: PostgresDispatchRepository(
                connection, candidate_gateway
            ),
            "outbox": PostgresOutboxRepository,
            "scheduled": PostgresScheduledRepository,
            "active_rides": PostgresActiveRideRepository,
            "arrival_waiting": PostgresArrivalWaitingRepository,
        }

    def unit_of_work(self) -> AyoPostgresUnitOfWork:
        return AyoPostgresUnitOfWork(self._engine, self._factories)
