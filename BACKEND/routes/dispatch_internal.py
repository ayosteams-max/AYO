from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.dispatch.outbox_worker import OutboxDeliveryWorker, OutboxRunResult
from BACKEND.dispatch.scheduler import (
    DispatchRecoveryCoordinator,
    ScheduledRecoveryResult,
    WorkerHealth,
    WorkerHealthSnapshot,
)
from BACKEND.identity.models import IdentityType


class WorkerHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    running: bool
    ready: bool
    consecutive_failures: int
    skipped_overlap_count: int
    last_started_at: datetime | None
    last_succeeded_at: datetime | None
    last_failure_reason: str | None

    @classmethod
    def from_snapshot(cls, value: WorkerHealthSnapshot) -> "WorkerHealthResponse":
        return cls(
            running=value.running,
            ready=value.ready(now=datetime.now(UTC)),
            consecutive_failures=value.consecutive_failures,
            skipped_overlap_count=value.skipped_overlap_count,
            last_started_at=value.last_started_at,
            last_succeeded_at=value.last_succeeded_at,
            last_failure_reason=value.last_failure_reason,
        )


def _worker_subject(request: Request) -> AuthorizationSubject:
    subject: AuthorizationSubject | None = getattr(
        request.state, "authorization_subject", None
    )
    if subject is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, {"code": "authentication_required"}
        )
    if subject.identity_type not in {IdentityType.SERVICE, IdentityType.ADMINISTRATOR}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, {"code": "access_denied"})
    return subject


def create_dispatch_internal_router(
    recovery: DispatchRecoveryCoordinator,
    outbox: OutboxDeliveryWorker,
    recovery_health: WorkerHealth,
    outbox_health: WorkerHealth,
) -> APIRouter:
    router = APIRouter(
        prefix="/internal/dispatch",
        tags=["dispatch-internal"],
        route_class=AuthorizationRoute,
    )

    @router.post("/workers/recovery/run", response_model=ScheduledRecoveryResult)
    @permission_required("dispatch.worker.recover", resource_type="dispatch_worker")
    def run_recovery(request: Request) -> ScheduledRecoveryResult:
        _worker_subject(request)
        return recovery.run_once()

    @router.post("/workers/outbox/run", response_model=OutboxRunResult)
    @permission_required("dispatch.worker.recover", resource_type="dispatch_worker")
    def run_outbox(request: Request) -> OutboxRunResult:
        _worker_subject(request)
        return outbox.run_once()

    @router.get("/workers/recovery/health", response_model=WorkerHealthResponse)
    @permission_required("dispatch.admin.health.read", resource_type="dispatch_worker")
    def worker_health(request: Request) -> WorkerHealthResponse:
        _worker_subject(request)
        return WorkerHealthResponse.from_snapshot(recovery_health.snapshot())

    @router.get("/workers/recovery/readiness", response_model=WorkerHealthResponse)
    @permission_required("dispatch.admin.health.read", resource_type="dispatch_worker")
    def worker_readiness(request: Request) -> WorkerHealthResponse:
        _worker_subject(request)
        result = WorkerHealthResponse.from_snapshot(recovery_health.snapshot())
        if not result.ready:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"code": "dispatch_worker_not_ready"},
            )
        return result

    @router.get("/workers/outbox/health", response_model=WorkerHealthResponse)
    @permission_required("dispatch.admin.health.read", resource_type="dispatch_worker")
    def outbox_worker_health(request: Request) -> WorkerHealthResponse:
        _worker_subject(request)
        return WorkerHealthResponse.from_snapshot(outbox_health.snapshot())

    return router
