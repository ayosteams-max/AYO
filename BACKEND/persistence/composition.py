from sqlalchemy import Engine

from BACKEND.persistence.active_ride_repository import PostgresActiveRideRepository
from BACKEND.persistence.arrival_waiting_repository import (
    PostgresArrivalWaitingRepository,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.authorization_repository import (
    PostgresAuthorizationRepository,
)
from BACKEND.persistence.booking_repository import PostgresBookingRepository
from BACKEND.persistence.canonical_preparation_repository import (
    PostgresCanonicalPreparationRepository,
)
from BACKEND.persistence.catalogue_repository import PostgresCatalogueRepository
from BACKEND.persistence.courier_dispatch_repository import (
    PostgresCourierDispatchRepository,
)
from BACKEND.persistence.courier_pickup_repository import (
    PostgresCourierPickupRepository,
)
from BACKEND.persistence.custody_repository import PostgresCustodyRepository
from BACKEND.persistence.delivery_repository import PostgresDeliveryRepository
from BACKEND.persistence.dispatch_repository import (
    DriverCandidateGateway,
    NoDriverCandidateGateway,
    PostgresDispatchRepository,
)
from BACKEND.persistence.driver_trust_repository import PostgresDriverTrustRepository
from BACKEND.persistence.eat_availability_repository import (
    PostgresEatAvailabilityRepository,
)
from BACKEND.persistence.field_operations_repository import (
    PostgresFieldOperationsRepository,
)
from BACKEND.persistence.field_performance_repository import (
    PostgresFieldPerformanceRepository,
)
from BACKEND.persistence.financial_hold_repository import (
    PostgresFinancialHoldRepository,
)
from BACKEND.persistence.financial_posting_repository import (
    PostgresFinancialPostingRepository,
)
from BACKEND.persistence.handoff_dispatch_repository import (
    PostgresHandoffDispatchRepository,
)
from BACKEND.persistence.identity_repository import (
    PostgresAuthenticationChallengeRepository,
    PostgresIdentityRepository,
    PostgresPasswordCredentialRepository,
    PostgresRefreshTokenRepository,
)
from BACKEND.persistence.ledger_repository import PostgresLedgerRepository
from BACKEND.persistence.localization_repository import PostgresLocalizationRepository
from BACKEND.persistence.merchant_order_repository import (
    PostgresMerchantOrderRepository,
)
from BACKEND.persistence.merchant_preparation_repository import (
    PostgresMerchantPreparationRepository,
)
from BACKEND.persistence.merchant_repository import PostgresMerchantRepository
from BACKEND.persistence.ordering_repository import PostgresOrderingRepository
from BACKEND.persistence.outbox_repository import PostgresOutboxRepository
from BACKEND.persistence.payment_repository import PostgresPaymentRepository
from BACKEND.persistence.post_trip_repository import PostgresPostTripRepository
from BACKEND.persistence.pricing_repository import PostgresPricingRepository
from BACKEND.persistence.rate_limit_repository import PostgresTokenBucketRateLimiter
from BACKEND.persistence.refund_repository import PostgresRefundRepository
from BACKEND.persistence.repositories import (
    PostgresLegacyWalletRepository,
    PostgresRideRepository,
)
from BACKEND.persistence.ride_request_repository import PostgresRideRequestRepository
from BACKEND.persistence.scheduled_repository import PostgresScheduledRepository
from BACKEND.persistence.session_repository import PostgresSessionRepository
from BACKEND.persistence.settlement_repository import PostgresSettlementRepository
from BACKEND.persistence.support_repository import PostgresSupportRepository
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork
from BACKEND.persistence.wallet_repository import PostgresWalletRepository
from BACKEND.persistence.worker_session_repository import (
    PostgresWorkerSessionRepository,
)


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
    def password_credentials(self) -> PostgresPasswordCredentialRepository:
        return self.repository(
            "password_credentials", PostgresPasswordCredentialRepository
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

    @property
    def driver_trust(self) -> PostgresDriverTrustRepository:
        return self.repository("driver_trust", PostgresDriverTrustRepository)

    @property
    def ride_requests(self) -> PostgresRideRequestRepository:
        return self.repository("ride_requests", PostgresRideRequestRepository)

    @property
    def handoff_dispatch(self) -> PostgresHandoffDispatchRepository:
        return self.repository("handoff_dispatch", PostgresHandoffDispatchRepository)

    @property
    def worker_sessions(self) -> PostgresWorkerSessionRepository:
        return self.repository("worker_sessions", PostgresWorkerSessionRepository)

    @property
    def localization(self) -> PostgresLocalizationRepository:
        return self.repository("localization", PostgresLocalizationRepository)

    @property
    def pricing(self) -> PostgresPricingRepository:
        return self.repository("pricing", PostgresPricingRepository)

    @property
    def booking(self) -> PostgresBookingRepository:
        return self.repository("booking", PostgresBookingRepository)

    @property
    def payments(self) -> PostgresPaymentRepository:
        return self.repository("payments", PostgresPaymentRepository)

    @property
    def refunds(self) -> PostgresRefundRepository:
        return self.repository("refunds", PostgresRefundRepository)

    @property
    def settlements(self) -> PostgresSettlementRepository:
        return self.repository("settlements", PostgresSettlementRepository)

    @property
    def financial_postings(self) -> PostgresFinancialPostingRepository:
        return self.repository("financial_postings", PostgresFinancialPostingRepository)

    @property
    def financial_holds(self) -> PostgresFinancialHoldRepository:
        return self.repository("financial_holds", PostgresFinancialHoldRepository)

    @property
    def wallets(self) -> PostgresWalletRepository:
        return self.repository("wallets", PostgresWalletRepository)

    @property
    def ledger(self) -> PostgresLedgerRepository:
        return self.repository("ledger", PostgresLedgerRepository)

    @property
    def post_trip(self) -> PostgresPostTripRepository:
        return self.repository("post_trip", PostgresPostTripRepository)

    @property
    def merchants(self) -> PostgresMerchantRepository:
        return self.repository("merchants", PostgresMerchantRepository)

    @property
    def catalogue(self) -> PostgresCatalogueRepository:
        return self.repository("catalogue", PostgresCatalogueRepository)

    @property
    def orders(self) -> PostgresOrderingRepository:
        return self.repository("orders", PostgresOrderingRepository)

    @property
    def eat_availability(self) -> PostgresEatAvailabilityRepository:
        return self.repository("eat_availability", PostgresEatAvailabilityRepository)

    @property
    def merchant_orders(self) -> PostgresMerchantOrderRepository:
        return self.repository("merchant_orders", PostgresMerchantOrderRepository)

    @property
    def preparation(self) -> PostgresMerchantPreparationRepository:
        return self.repository("preparation", PostgresMerchantPreparationRepository)

    @property
    def preparation_cases(self) -> PostgresCanonicalPreparationRepository:
        return self.repository(
            "preparation_cases", PostgresCanonicalPreparationRepository
        )

    @property
    def courier_dispatch(self) -> PostgresCourierDispatchRepository:
        return self.repository("courier_dispatch", PostgresCourierDispatchRepository)

    @property
    def courier_pickup(self) -> PostgresCourierPickupRepository:
        return self.repository("courier_pickup", PostgresCourierPickupRepository)

    @property
    def custody(self) -> PostgresCustodyRepository:
        return self.repository("custody", PostgresCustodyRepository)

    @property
    def delivery(self) -> PostgresDeliveryRepository:
        return self.repository("delivery", PostgresDeliveryRepository)

    @property
    def field_operations(self) -> PostgresFieldOperationsRepository:
        return self.repository("field_operations", PostgresFieldOperationsRepository)

    @property
    def field_performance(self) -> PostgresFieldPerformanceRepository:
        return self.repository("field_performance", PostgresFieldPerformanceRepository)


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
            "password_credentials": PostgresPasswordCredentialRepository,
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
            "driver_trust": PostgresDriverTrustRepository,
            "ride_requests": PostgresRideRequestRepository,
            "handoff_dispatch": PostgresHandoffDispatchRepository,
            "worker_sessions": PostgresWorkerSessionRepository,
            "localization": PostgresLocalizationRepository,
            "pricing": PostgresPricingRepository,
            "booking": PostgresBookingRepository,
            "payments": PostgresPaymentRepository,
            "refunds": PostgresRefundRepository,
            "settlements": PostgresSettlementRepository,
            "financial_postings": PostgresFinancialPostingRepository,
            "financial_holds": PostgresFinancialHoldRepository,
            "wallets": PostgresWalletRepository,
            "ledger": PostgresLedgerRepository,
            "post_trip": PostgresPostTripRepository,
            "merchants": PostgresMerchantRepository,
            "catalogue": PostgresCatalogueRepository,
            "orders": PostgresOrderingRepository,
            "eat_availability": PostgresEatAvailabilityRepository,
            "merchant_orders": PostgresMerchantOrderRepository,
            "preparation": PostgresMerchantPreparationRepository,
            "preparation_cases": PostgresCanonicalPreparationRepository,
            "courier_dispatch": PostgresCourierDispatchRepository,
            "courier_pickup": PostgresCourierPickupRepository,
            "custody": PostgresCustodyRepository,
            "delivery": PostgresDeliveryRepository,
            "field_operations": PostgresFieldOperationsRepository,
            "field_performance": PostgresFieldPerformanceRepository,
        }

    def unit_of_work(self) -> AyoPostgresUnitOfWork:
        return AyoPostgresUnitOfWork(self._engine, self._factories)
