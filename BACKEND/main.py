from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from BACKEND.active_ride.application import ActiveRideApplication
from BACKEND.authorization.enforcement import (
    AuthorizationContextMiddleware,
    AuthorizationEnforcer,
    TrustedSubjectResolver,
)
from BACKEND.config.settings import Settings, settings
from BACKEND.dispatch.api_security import (
    DispatchRateLimitBoundary,
    RequestSizeLimitMiddleware,
)
from BACKEND.dispatch.application import DispatchApplication
from BACKEND.dispatch.outbox_worker import OutboxDeliveryWorker
from BACKEND.dispatch.scheduler import DispatchRecoveryCoordinator, WorkerHealth
from BACKEND.observability import MetricsSink, NullMetricsSink
from BACKEND.routes.active_rides import create_active_ride_router
from BACKEND.routes.dispatch import create_dispatch_router
from BACKEND.routes.dispatch_internal import create_dispatch_internal_router
from BACKEND.routes.driver_offer import router as driver_offer_router
from BACKEND.routes.ride import router as ride_router
from BACKEND.routes.ride_status import router as ride_status_router
from BACKEND.routes.scheduled import create_scheduled_router
from BACKEND.routes.wallet import router as wallet_router
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


def create_app(
    configuration: Settings | None = None,
    *,
    dispatch: DispatchActivation | None = None,
    scheduled_dispatch: ScheduledDispatchActivation | None = None,
    active_ride: ActiveRideActivation | None = None,
) -> FastAPI:
    configured = configuration or settings
    application = FastAPI(
        title=configured.APP_NAME,
        version=configured.APP_VERSION,
    )
    application.include_router(ride_router, prefix=configured.API_PREFIX)
    application.include_router(driver_offer_router, prefix=configured.API_PREFIX)
    application.include_router(ride_status_router, prefix=configured.API_PREFIX)
    application.include_router(wallet_router, prefix=configured.API_PREFIX)

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
        if not configured.DISPATCH_ENABLED:
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
        if (
            not configured.DISPATCH_ENABLED
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

    return application


app = create_app()
