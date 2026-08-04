from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from BACKEND.active_ride.application import ActiveRideApplication
from BACKEND.active_ride.lifecycle import ActiveRideLifecycleApplication
from BACKEND.arrival_waiting.application import ArrivalWaitingApplication
from BACKEND.authorization.enforcement import (
    AuthorizationContextMiddleware,
    AuthorizationEnforcer,
    TrustedSubjectResolver,
)
from BACKEND.booking.application import BookingApplication
from BACKEND.catalogue.application import UniversalCatalogueApplication
from BACKEND.config.settings import Settings, settings
from BACKEND.courier_dispatch.application import CourierDispatchApplication
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.custody.application import CustodyApplication
from BACKEND.delivery_verification.application import DeliveryApplication
from BACKEND.dispatch.api_security import (
    DispatchRateLimitBoundary,
    RequestSizeLimitMiddleware,
)
from BACKEND.dispatch.application import DispatchApplication
from BACKEND.dispatch.outbox_worker import OutboxDeliveryWorker
from BACKEND.dispatch.runtime import CanonicalDispatchApplication
from BACKEND.dispatch.scheduler import DispatchRecoveryCoordinator, WorkerHealth
from BACKEND.dispatch.worker_session import WorkerSessionApplication
from BACKEND.engineering.runtime import EngineeringRuntime
from BACKEND.field_operations.application import FieldOperationsApplication
from BACKEND.field_performance.application import FieldPerformanceApplication
from BACKEND.identity.runtime import AuthenticationRuntime
from BACKEND.merchant.application import MerchantApplication
from BACKEND.merchant_orders.application import MerchantOrderApplication
from BACKEND.merchant_preparation.application import MerchantPreparationApplication
from BACKEND.observability import MetricsSink, NullMetricsSink
from BACKEND.ordering.application import OrderingApplication
from BACKEND.persistence.config import DatabaseSettings
from BACKEND.persistence.engine import create_postgres_engine
from BACKEND.persistence.logging import configure_structured_logging
from BACKEND.post_trip.application import PostTripApplication
from BACKEND.pricing.mobile_quotes import MobileCashQuoteApplication
from BACKEND.routes.active_rides import create_active_ride_router
from BACKEND.routes.arrival_waiting_routes import create_arrival_waiting_router
from BACKEND.routes.authentication import create_authentication_router
from BACKEND.routes.booking import create_booking_router
from BACKEND.routes.canonical_dispatch import create_canonical_dispatch_router
from BACKEND.routes.catalogue import create_catalogue_router
from BACKEND.routes.courier_dispatch import create_courier_dispatch_router
from BACKEND.routes.courier_pickup import create_courier_pickup_router
from BACKEND.routes.custody import create_custody_router
from BACKEND.routes.delivery import create_delivery_router
from BACKEND.routes.dispatch import create_dispatch_router
from BACKEND.routes.dispatch_internal import create_dispatch_internal_router
from BACKEND.routes.field_operations import create_field_operations_router
from BACKEND.routes.field_performance import create_field_performance_router
from BACKEND.routes.merchant import create_merchant_router
from BACKEND.routes.merchant_orders import create_merchant_order_router
from BACKEND.routes.merchant_preparation import create_merchant_preparation_router
from BACKEND.routes.mobile_quotes import create_mobile_quote_router
from BACKEND.routes.ordering import (
    create_ordering_router,
    create_public_commerce_router,
)
from BACKEND.routes.post_trip import create_post_trip_router
from BACKEND.routes.scheduled import create_scheduled_router
from BACKEND.routes.trip_execution import create_trip_execution_router
from BACKEND.scheduled.integration import ScheduledIntegrationApplication


@dataclass(frozen=True, slots=True)
class DispatchActivation:
    application: DispatchApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer
    rate_limiter: DispatchRateLimitBoundary
    recovery_coordinator: DispatchRecoveryCoordinator
    outbox_worker: OutboxDeliveryWorker
    recovery_health: WorkerHealth
    outbox_health: WorkerHealth
    metrics: MetricsSink


@dataclass(frozen=True, slots=True)
class AuthenticationActivation:
    runtime: AuthenticationRuntime
    subject_resolver: TrustedSubjectResolver


@dataclass(frozen=True, slots=True)
class ScheduledDispatchActivation:
    application: ScheduledIntegrationApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer
    rate_limiter: DispatchRateLimitBoundary
    metrics: MetricsSink


@dataclass(frozen=True, slots=True)
class ActiveRideActivation:
    application: ActiveRideApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer
    rate_limiter: DispatchRateLimitBoundary
    metrics: MetricsSink
    lifecycle: ActiveRideLifecycleApplication | None = None


@dataclass(frozen=True, slots=True)
class ArrivalWaitingActivation:
    application: ArrivalWaitingApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer
    rate_limiter: DispatchRateLimitBoundary
    metrics: MetricsSink


@dataclass(frozen=True, slots=True)
class MobileCashQuoteActivation:
    application: MobileCashQuoteApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class RiderBookingActivation:
    application: BookingApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class CanonicalDispatchActivation:
    application: CanonicalDispatchApplication
    worker_sessions: WorkerSessionApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer
    rate_limiter: DispatchRateLimitBoundary
    metrics: MetricsSink


@dataclass(frozen=True, slots=True)
class PostTripActivation:
    application: PostTripApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class MerchantActivation:
    application: MerchantApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class CatalogueActivation:
    application: UniversalCatalogueApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class OrderingActivation:
    application: OrderingApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class MerchantOrderActivation:
    application: MerchantOrderApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class MerchantPreparationActivation:
    application: MerchantPreparationApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class CourierDispatchPlatformActivation:
    application: CourierDispatchApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class CourierPickupPlatformActivation:
    application: CourierPickupApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class CustodyPlatformActivation:
    application: CustodyApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class DeliveryPlatformActivation:
    application: DeliveryApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer


@dataclass(frozen=True, slots=True)
class FieldOperationsPlatformActivation:
    application: FieldOperationsApplication
    subject_resolver: TrustedSubjectResolver
    authorization_enforcer: AuthorizationEnforcer
    performance_application: FieldPerformanceApplication | None = None


def create_app(
    configuration: Settings | None = None,
    *,
    authentication: AuthenticationActivation | None = None,
    dispatch: DispatchActivation | None = None,
    scheduled_dispatch: ScheduledDispatchActivation | None = None,
    active_ride: ActiveRideActivation | None = None,
    arrival_waiting: ArrivalWaitingActivation | None = None,
    mobile_cash_quote: MobileCashQuoteActivation | None = None,
    rider_booking: RiderBookingActivation | None = None,
    canonical_dispatch: CanonicalDispatchActivation | None = None,
    post_trip: PostTripActivation | None = None,
    merchant: MerchantActivation | None = None,
    catalogue: CatalogueActivation | None = None,
    ordering: OrderingActivation | None = None,
    merchant_orders: MerchantOrderActivation | None = None,
    merchant_preparation: MerchantPreparationActivation | None = None,
    courier_dispatch_platform: CourierDispatchPlatformActivation | None = None,
    courier_pickup_platform: CourierPickupPlatformActivation | None = None,
    custody_platform: CustodyPlatformActivation | None = None,
    delivery_platform: DeliveryPlatformActivation | None = None,
    field_operations_platform: FieldOperationsPlatformActivation | None = None,
    engineering_runtime: EngineeringRuntime | None = None,
) -> FastAPI:
    configured = configuration or settings
    configure_structured_logging(configured.LOG_LEVEL)
    runtime = engineering_runtime
    if runtime is None:
        engine = None
        if configured.PERSISTENCE_ENABLED:
            engine = create_postgres_engine(DatabaseSettings())
        runtime = EngineeringRuntime(
            engine,
            persistence_required=configured.PERSISTENCE_ENABLED,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runtime.start()
        try:
            yield
        finally:
            runtime.close()

    application = FastAPI(
        title=configured.APP_NAME,
        version=configured.APP_VERSION,
        lifespan=lifespan,
    )
    application.state.engineering_runtime = runtime
    if configured.AUTHENTICATION_ENABLED:
        if authentication is None:
            raise RuntimeError(
                "Enabled authentication requires explicit secure activation dependencies"
            )
        application.include_router(
            create_authentication_router(
                authentication.runtime, authentication.subject_resolver
            ),
            prefix=configured.API_PREFIX,
        )
        application.add_middleware(
            RequestSizeLimitMiddleware,
            maximum_bytes=configured.AUTHENTICATION_MAX_REQUEST_BYTES,
        )
    if configured.DISPATCH_ENABLED:
        if dispatch is None:
            raise RuntimeError(
                "Enabled dispatch requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = dispatch.authorization_enforcer
        application.state.dispatch_rate_limiter = dispatch.rate_limiter
        application.state.dispatch_metrics = dispatch.metrics
        application.include_router(
            create_dispatch_router(dispatch.application, metrics=dispatch.metrics),
            prefix=configured.API_PREFIX,
        )
        application.include_router(
            create_dispatch_internal_router(
                dispatch.recovery_coordinator,
                dispatch.outbox_worker,
                dispatch.recovery_health,
                dispatch.outbox_health,
            ),
            prefix=configured.API_PREFIX,
        )
        application.add_middleware(
            AuthorizationContextMiddleware, resolver=dispatch.subject_resolver
        )
        application.add_middleware(
            RequestSizeLimitMiddleware,
            maximum_bytes=configured.DISPATCH_MAX_REQUEST_BYTES,
        )
    else:
        application.state.dispatch_metrics = NullMetricsSink()

    if configured.CANONICAL_DISPATCH_ENABLED:
        if canonical_dispatch is None:
            raise RuntimeError(
                "Enabled canonical dispatch requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            canonical_dispatch.authorization_enforcer
        )
        application.state.dispatch_rate_limiter = canonical_dispatch.rate_limiter
        application.state.canonical_dispatch_metrics = canonical_dispatch.metrics
        application.include_router(
            create_canonical_dispatch_router(
                canonical_dispatch.application, canonical_dispatch.worker_sessions
            ),
            prefix=configured.API_PREFIX,
        )
        if not configured.DISPATCH_ENABLED:
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=canonical_dispatch.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.DISPATCH_MAX_REQUEST_BYTES,
            )
    else:
        application.state.canonical_dispatch_metrics = NullMetricsSink()

    if configured.SCHEDULED_DISPATCH_ENABLED:
        if scheduled_dispatch is None:
            raise RuntimeError(
                "Enabled scheduled dispatch requires explicit secure dependencies"
            )
        application.state.authorization_enforcer = (
            scheduled_dispatch.authorization_enforcer
        )
        application.state.dispatch_rate_limiter = scheduled_dispatch.rate_limiter
        application.state.scheduled_dispatch_metrics = scheduled_dispatch.metrics
        application.include_router(
            create_scheduled_router(scheduled_dispatch.application),
            prefix=configured.API_PREFIX,
        )
        if not (configured.DISPATCH_ENABLED or configured.CANONICAL_DISPATCH_ENABLED):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=scheduled_dispatch.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.SCHEDULED_DISPATCH_MAX_REQUEST_BYTES,
            )
    else:
        application.state.scheduled_dispatch_metrics = NullMetricsSink()

    if configured.ACTIVE_RIDE_ENABLED:
        if active_ride is None:
            raise RuntimeError(
                "Enabled active ride requires explicit secure dependencies"
            )
        application.state.authorization_enforcer = active_ride.authorization_enforcer
        application.state.dispatch_rate_limiter = active_ride.rate_limiter
        application.state.active_ride_metrics = active_ride.metrics
        application.include_router(
            create_active_ride_router(active_ride.application),
            prefix=configured.API_PREFIX,
        )
        if active_ride.lifecycle is not None:
            application.include_router(
                create_trip_execution_router(active_ride.lifecycle),
                prefix=configured.API_PREFIX,
            )
        if (
            not configured.DISPATCH_ENABLED
            and not configured.CANONICAL_DISPATCH_ENABLED
            and not configured.SCHEDULED_DISPATCH_ENABLED
        ):
            application.add_middleware(
                AuthorizationContextMiddleware, resolver=active_ride.subject_resolver
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.ACTIVE_RIDE_MAX_REQUEST_BYTES,
            )
    else:
        application.state.active_ride_metrics = NullMetricsSink()

    if configured.ARRIVAL_WAITING_ENABLED:
        if arrival_waiting is None:
            raise RuntimeError(
                "Enabled arrival/waiting requires explicit secure dependencies"
            )
        application.state.authorization_enforcer = (
            arrival_waiting.authorization_enforcer
        )
        application.state.dispatch_rate_limiter = arrival_waiting.rate_limiter
        application.state.arrival_waiting_metrics = arrival_waiting.metrics
        application.include_router(
            create_arrival_waiting_router(arrival_waiting.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=arrival_waiting.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.ARRIVAL_WAITING_MAX_REQUEST_BYTES,
            )
    else:
        application.state.arrival_waiting_metrics = NullMetricsSink()

    if configured.MOBILE_CASH_QUOTE_ENABLED:
        if mobile_cash_quote is None:
            raise RuntimeError(
                "Enabled mobile cash quotes require explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            mobile_cash_quote.authorization_enforcer
        )
        application.include_router(
            create_mobile_quote_router(mobile_cash_quote.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=mobile_cash_quote.subject_resolver,
            )

    if configured.RIDER_BOOKING_ENABLED:
        if rider_booking is None:
            raise RuntimeError(
                "Enabled rider booking requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = rider_booking.authorization_enforcer
        application.include_router(
            create_booking_router(
                rider_booking.application, rider_booking.subject_resolver
            ),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware, resolver=rider_booking.subject_resolver
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.RIDER_BOOKING_MAX_REQUEST_BYTES,
            )

    if configured.POST_TRIP_ENABLED:
        if post_trip is None:
            raise RuntimeError(
                "Enabled post-trip requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = post_trip.authorization_enforcer
        application.include_router(
            create_post_trip_router(post_trip.application), prefix=configured.API_PREFIX
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware, resolver=post_trip.subject_resolver
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.POST_TRIP_MAX_REQUEST_BYTES,
            )

    if configured.MERCHANT_PLATFORM_ENABLED:
        if merchant is None:
            raise RuntimeError(
                "Enabled Merchant Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = merchant.authorization_enforcer
        application.include_router(
            create_merchant_router(merchant.application), prefix=configured.API_PREFIX
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware, resolver=merchant.subject_resolver
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.MERCHANT_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.CATALOGUE_PLATFORM_ENABLED:
        if catalogue is None:
            raise RuntimeError(
                "Enabled Catalogue Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = catalogue.authorization_enforcer
        application.include_router(
            create_catalogue_router(catalogue.application), prefix=configured.API_PREFIX
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware, resolver=catalogue.subject_resolver
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.CATALOGUE_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.ORDERING_PLATFORM_ENABLED:
        if ordering is None:
            raise RuntimeError(
                "Enabled Ordering Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = ordering.authorization_enforcer
        application.include_router(
            create_public_commerce_router(ordering.application),
            prefix=configured.API_PREFIX,
        )
        application.include_router(
            create_ordering_router(ordering.application), prefix=configured.API_PREFIX
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware, resolver=ordering.subject_resolver
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.ORDERING_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.MERCHANT_ORDER_MANAGEMENT_ENABLED:
        if merchant_orders is None:
            raise RuntimeError(
                "Enabled Merchant Order Management requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            merchant_orders.authorization_enforcer
        )
        application.include_router(
            create_merchant_order_router(merchant_orders.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=merchant_orders.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.MERCHANT_ORDER_MANAGEMENT_MAX_REQUEST_BYTES,
            )

    if configured.MERCHANT_PREPARATION_ENABLED:
        if merchant_preparation is None:
            raise RuntimeError(
                "Enabled Merchant Preparation requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            merchant_preparation.authorization_enforcer
        )
        application.include_router(
            create_merchant_preparation_router(merchant_preparation.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
                configured.MERCHANT_ORDER_MANAGEMENT_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=merchant_preparation.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.MERCHANT_PREPARATION_MAX_REQUEST_BYTES,
            )

    if configured.COURIER_DISPATCH_PLATFORM_ENABLED:
        if courier_dispatch_platform is None:
            raise RuntimeError(
                "Enabled Courier Dispatch Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            courier_dispatch_platform.authorization_enforcer
        )
        application.include_router(
            create_courier_dispatch_router(courier_dispatch_platform.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
                configured.MERCHANT_ORDER_MANAGEMENT_ENABLED,
                configured.MERCHANT_PREPARATION_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=courier_dispatch_platform.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.COURIER_DISPATCH_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.COURIER_PICKUP_PLATFORM_ENABLED:
        if courier_pickup_platform is None:
            raise RuntimeError(
                "Enabled Courier Pickup Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            courier_pickup_platform.authorization_enforcer
        )
        application.include_router(
            create_courier_pickup_router(courier_pickup_platform.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
                configured.MERCHANT_ORDER_MANAGEMENT_ENABLED,
                configured.MERCHANT_PREPARATION_ENABLED,
                configured.COURIER_DISPATCH_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=courier_pickup_platform.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.COURIER_PICKUP_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.CUSTODY_PLATFORM_ENABLED:
        if custody_platform is None:
            raise RuntimeError(
                "Enabled Custody Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            custody_platform.authorization_enforcer
        )
        application.include_router(
            create_custody_router(custody_platform.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
                configured.MERCHANT_ORDER_MANAGEMENT_ENABLED,
                configured.MERCHANT_PREPARATION_ENABLED,
                configured.COURIER_DISPATCH_PLATFORM_ENABLED,
                configured.COURIER_PICKUP_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=custody_platform.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.CUSTODY_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.DELIVERY_PLATFORM_ENABLED:
        if delivery_platform is None:
            raise RuntimeError(
                "Enabled Delivery Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            delivery_platform.authorization_enforcer
        )
        application.include_router(
            create_delivery_router(delivery_platform.application),
            prefix=configured.API_PREFIX,
        )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
                configured.MERCHANT_ORDER_MANAGEMENT_ENABLED,
                configured.MERCHANT_PREPARATION_ENABLED,
                configured.COURIER_DISPATCH_PLATFORM_ENABLED,
                configured.COURIER_PICKUP_PLATFORM_ENABLED,
                configured.CUSTODY_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=delivery_platform.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.DELIVERY_PLATFORM_MAX_REQUEST_BYTES,
            )

    if configured.FIELD_OPERATIONS_PLATFORM_ENABLED:
        if field_operations_platform is None:
            raise RuntimeError(
                "Enabled Field Operations Platform requires explicit secure activation dependencies"
            )
        application.state.authorization_enforcer = (
            field_operations_platform.authorization_enforcer
        )
        application.include_router(
            create_field_operations_router(field_operations_platform.application),
            prefix=configured.API_PREFIX,
        )
        if field_operations_platform.performance_application is not None:
            application.include_router(
                create_field_performance_router(
                    field_operations_platform.performance_application
                ),
                prefix=configured.API_PREFIX,
            )
        if not any(
            (
                configured.DISPATCH_ENABLED,
                configured.CANONICAL_DISPATCH_ENABLED,
                configured.SCHEDULED_DISPATCH_ENABLED,
                configured.ACTIVE_RIDE_ENABLED,
                configured.ARRIVAL_WAITING_ENABLED,
                configured.MOBILE_CASH_QUOTE_ENABLED,
                configured.RIDER_BOOKING_ENABLED,
                configured.POST_TRIP_ENABLED,
                configured.MERCHANT_PLATFORM_ENABLED,
                configured.CATALOGUE_PLATFORM_ENABLED,
                configured.ORDERING_PLATFORM_ENABLED,
                configured.MERCHANT_ORDER_MANAGEMENT_ENABLED,
                configured.MERCHANT_PREPARATION_ENABLED,
                configured.COURIER_DISPATCH_PLATFORM_ENABLED,
                configured.COURIER_PICKUP_PLATFORM_ENABLED,
                configured.CUSTODY_PLATFORM_ENABLED,
                configured.DELIVERY_PLATFORM_ENABLED,
            )
        ):
            application.add_middleware(
                AuthorizationContextMiddleware,
                resolver=field_operations_platform.subject_resolver,
            )
            application.add_middleware(
                RequestSizeLimitMiddleware,
                maximum_bytes=configured.FIELD_OPERATIONS_PLATFORM_MAX_REQUEST_BYTES,
            )

    @application.exception_handler(HTTPException)
    async def stable_http_error(request: Request, error: HTTPException) -> JSONResponse:
        del request
        detail = error.detail
        payload = (
            detail
            if isinstance(detail, dict) and "code" in detail
            else {"code": "request_rejected"}
        )
        return JSONResponse(
            {"error": payload}, status_code=error.status_code, headers=error.headers
        )

    @application.exception_handler(RequestValidationError)
    async def stable_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request, error
        return JSONResponse({"error": {"code": "validation_failed"}}, status_code=422)

    @application.get("/")
    def home() -> dict[str, str]:
        return {
            "message": f"Welcome to {configured.APP_NAME}!",
            "status": "Backend is running successfully.",
        }

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    @application.get("/livez", include_in_schema=False)
    def liveness(response: Response) -> dict[str, str]:
        if not runtime.live:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_live"}
        return {"status": "live"}

    @application.get("/readyz", include_in_schema=False)
    def readiness(response: Response) -> dict[str, str]:
        result = runtime.readiness()
        if not result.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        payload = {
            "status": "ready" if result.ready else "not_ready",
            "database": result.database,
            "schema": result.schema,
        }
        if result.reason is not None:
            payload["reason"] = result.reason
        return payload

    return application


app = create_app()
