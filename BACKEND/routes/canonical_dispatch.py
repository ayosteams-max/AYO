from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.dispatch.api_security import require_rate_limit
from BACKEND.dispatch.runtime import CanonicalDispatchApplication
from BACKEND.dispatch.worker_models import WorkerCapabilitySession, WorkerSessionState
from BACKEND.dispatch.worker_session import WorkerSessionApplication
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict


class DriverModeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    vehicle_id: UUID
    service_zone_id: UUID


class DriverModeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: WorkerSessionState
    capability: str
    vehicle_id: UUID | None
    service_zone_id: UUID | None
    version: int

    @classmethod
    def from_session(cls, item: WorkerCapabilitySession) -> "DriverModeResponse":
        return cls(
            state=item.state,
            capability=item.capability.value,
            vehicle_id=item.vehicle_id,
            service_zone_id=item.service_zone_id,
            version=item.version,
        )


class CanonicalOfferResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    offer_id: UUID
    handoff_id: UUID
    expires_at: datetime
    version: int
    pickup_eta_seconds: int
    countdown_server_time: datetime


class OfferDecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int


class RiderDispatchStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_request_id: UUID
    state: str
    assigned: bool
    next_step: str
    active_ride_id: UUID | None = None


def _subject(request: Request, expected: IdentityType) -> AuthorizationSubject:
    subject = getattr(request.state, "authorization_subject", None)
    if subject is None:
        raise HTTPException(401, {"code": "authentication_required"})
    if subject.identity_type is not expected:
        raise HTTPException(403, {"code": "access_denied"})
    return subject


def create_canonical_dispatch_router(
    dispatch: CanonicalDispatchApplication,
    worker_sessions: WorkerSessionApplication,
) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/dispatch",
        tags=["canonical-dispatch"],
        route_class=AuthorizationRoute,
    )

    @router.put("/driver-mode", response_model=DriverModeResponse)
    @permission_required(
        "dispatch.driver_mode.manage_own", resource_type="worker_session"
    )
    def start_driver_mode(
        command: DriverModeRequest, request: Request
    ) -> DriverModeResponse:
        subject = _subject(request, IdentityType.DRIVER)
        require_rate_limit(request, subject, "driver_mode")
        try:
            item = worker_sessions.start_ride_driver(
                subject=subject,
                vehicle_id=command.vehicle_id,
                service_zone_id=command.service_zone_id,
                at=datetime.now(UTC),
            )
        except RuntimeError as error:
            raise HTTPException(409, {"code": str(error)}) from error
        return DriverModeResponse.from_session(item)

    @router.delete("/driver-mode", response_model=DriverModeResponse)
    @permission_required(
        "dispatch.driver_mode.manage_own", resource_type="worker_session"
    )
    def stop_driver_mode(request: Request) -> DriverModeResponse:
        subject = _subject(request, IdentityType.DRIVER)
        require_rate_limit(request, subject, "driver_mode")
        try:
            item = worker_sessions.stop_ride_driver(
                subject=subject, at=datetime.now(UTC)
            )
        except RuntimeError as error:
            raise HTTPException(409, {"code": str(error)}) from error
        return DriverModeResponse.from_session(item)

    @router.get("/offers/current", response_model=CanonicalOfferResponse | None)
    @permission_required(
        "dispatch.canonical.offer.respond", resource_type="driver_offer"
    )
    def current_offer(request: Request) -> CanonicalOfferResponse | None:
        subject = _subject(request, IdentityType.DRIVER)
        require_rate_limit(request, subject, "offer_lookup")
        offer = dispatch.offer_for_driver(subject.identity_id)
        if offer is None:
            return None
        return CanonicalOfferResponse(
            offer_id=offer.offer_id,
            handoff_id=offer.handoff_id,
            expires_at=offer.expires_at,
            version=offer.version,
            pickup_eta_seconds=offer.pickup_cost_seconds,
            countdown_server_time=datetime.now(UTC),
        )

    def respond(
        *,
        offer_id: UUID,
        command: OfferDecisionRequest,
        request: Request,
        idempotency_key: str,
        accept: bool,
    ) -> dict[str, object]:
        subject = _subject(request, IdentityType.DRIVER)
        require_rate_limit(request, subject, "offer_response")
        try:
            assignment_id = dispatch.respond(
                subject=subject,
                offer_id=offer_id,
                accept=accept,
                expected_version=command.expected_version,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        except HandoffConflict as error:
            raise HTTPException(409, {"code": "offer_no_longer_available"}) from error
        return {
            "outcome": "accepted" if accept else "declined",
            "assignment_id": assignment_id,
            "active_ride_id": dispatch.active_ride_id_for_assignment(assignment_id)
            if assignment_id is not None
            else None,
            "navigation_started": False,
        }

    @router.post("/offers/{offer_id}/accept", status_code=status.HTTP_200_OK)
    @permission_required(
        "dispatch.canonical.offer.respond",
        resource_type="driver_offer",
        resource_id_parameter="offer_id",
    )
    def accept_offer(
        offer_id: UUID,
        command: OfferDecisionRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        return respond(
            offer_id=offer_id,
            command=command,
            request=request,
            idempotency_key=idempotency_key,
            accept=True,
        )

    @router.post("/offers/{offer_id}/decline", status_code=status.HTTP_200_OK)
    @permission_required(
        "dispatch.canonical.offer.respond",
        resource_type="driver_offer",
        resource_id_parameter="offer_id",
    )
    def decline_offer(
        offer_id: UUID,
        command: OfferDecisionRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        return respond(
            offer_id=offer_id,
            command=command,
            request=request,
            idempotency_key=idempotency_key,
            accept=False,
        )

    @router.get("/rides/{ride_request_id}", response_model=RiderDispatchStatus)
    @permission_required(
        "ride_request.create",
        resource_type="canonical_ride_request",
        resource_id_parameter="ride_request_id",
    )
    def rider_status(ride_request_id: UUID, request: Request) -> RiderDispatchStatus:
        subject = _subject(request, IdentityType.RIDER)
        require_rate_limit(request, subject, "ride_active")
        handoff = dispatch.status_for_rider(
            rider_id=subject.identity_id, ride_request_id=ride_request_id
        )
        if handoff is None:
            raise HTTPException(404, {"code": "ride_not_found"})
        return RiderDispatchStatus(
            ride_request_id=ride_request_id,
            state=handoff.state.value,
            assigned=handoff.assigned_driver_id is not None,
            next_step=(
                "driver_assigned"
                if handoff.assigned_driver_id
                else "no_driver_available"
                if handoff.state.value == "no_driver"
                else "searching_for_driver"
            ),
            active_ride_id=dispatch.active_ride_id_for_request(
                rider_id=subject.identity_id, ride_request_id=ride_request_id
            )
            if handoff.assigned_driver_id is not None
            else None,
        )

    return router
