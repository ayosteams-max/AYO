from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from BACKEND.arrival_waiting.application import (
    ArrivalCommand,
    ArrivalWaitingApplication,
    ContinuityCommand,
    EvidenceCommand,
    ReadinessCommand,
    RiderPresentCommand,
    StartWaitingCommand,
)
from BACKEND.arrival_waiting.engine import ArrivalWaitingConflict
from BACKEND.arrival_waiting.models import WalkingGuidanceRequest
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.dispatch.api_security import require_rate_limit


def _subject(request: Request) -> AuthorizationSubject:
    subject = getattr(request.state, "authorization_subject", None)
    if subject is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return cast(AuthorizationSubject, subject)


def _call[Result](operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except ArrivalWaitingConflict as error:
        code = str(error).split(":", 1)[0]
        status = (
            404
            if code == "ride_not_found"
            else 403
            if code in {"access_denied", "driver_required", "rider_required"}
            else 409
        )
        allowed = {
            "ride_not_found",
            "access_denied",
            "driver_required",
            "rider_required",
            "stale_ride_version",
            "stale_waiting_session",
            "stale_location_observation",
            "idempotency_conflict",
            "arrival_not_verified",
            "waiting_already_started",
            "waiting_not_started",
            "waiting_policy_unavailable",
            "waiting_policy_ambiguous",
            "pickup_or_assignment_mismatch",
        }
        raise HTTPException(
            status, {"code": code if code in allowed else "arrival_waiting_conflict"}
        ) from error


def create_arrival_waiting_router(application: ArrivalWaitingApplication) -> APIRouter:
    router = APIRouter(
        prefix="/arrival-waiting",
        tags=["arrival-waiting"],
        route_class=AuthorizationRoute,
    )

    def read(request: Request) -> AuthorizationSubject:
        subject = _subject(request)
        require_rate_limit(request, subject, "arrival_waiting_read")
        return subject

    def command(request: Request) -> AuthorizationSubject:
        subject = _subject(request)
        require_rate_limit(request, subject, "arrival_waiting_command")
        return subject

    @router.get("/{ride_id}/arrival")
    @permission_required(
        "arrival_waiting.read",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def arrival(ride_id: UUID, request: Request) -> dict[str, Any]:
        return _call(lambda: application.arrival(read(request), ride_id))

    @router.post("/{ride_id}/driver/location")
    @permission_required(
        "arrival_waiting.driver.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def location(
        ride_id: UUID, body: ArrivalCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.submit_arrival(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    @router.get("/{ride_id}/readiness")
    @permission_required(
        "arrival_waiting.read",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def readiness(ride_id: UUID, request: Request) -> dict[str, Any]:
        return _call(lambda: application.readiness(read(request), ride_id))

    @router.post("/{ride_id}/readiness/evaluate")
    @permission_required(
        "arrival_waiting.rider.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def evaluate_readiness(
        ride_id: UUID, body: ReadinessCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.evaluate_rider_readiness(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    @router.get("/{ride_id}/waiting")
    @router.get("/{ride_id}/countdown")
    @permission_required(
        "arrival_waiting.read",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def waiting(ride_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.waiting(read(request), ride_id, now=datetime.now(UTC))
        )

    @router.post("/{ride_id}/waiting/start")
    @permission_required(
        "arrival_waiting.driver.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def start(
        ride_id: UUID, body: StartWaitingCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.start(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    @router.post("/{ride_id}/waiting/continuity")
    @router.post("/{ride_id}/waiting/pause-or-invalidate")
    @permission_required(
        "arrival_waiting.driver.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def continuity(
        ride_id: UUID, body: ContinuityCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.continuity(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    @router.post("/{ride_id}/rider-present")
    @permission_required(
        "arrival_waiting.rider.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def rider_present(
        ride_id: UUID, body: RiderPresentCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.rider_present(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    @router.post("/{ride_id}/evidence/evaluate")
    @permission_required(
        "arrival_waiting.driver.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def evaluate_evidence(
        ride_id: UUID, body: EvidenceCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.evaluate_no_show(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    @router.get("/{ride_id}/evidence")
    @permission_required(
        "arrival_waiting.read",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def evidence(ride_id: UUID, request: Request) -> dict[str, Any]:
        return _call(lambda: application.evidence(read(request), ride_id))

    @router.get("/{ride_id}/landmarks/{landmark_id}")
    @permission_required(
        "arrival_waiting.read",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def landmark(ride_id: UUID, landmark_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.landmark(
                read(request), ride_id, landmark_id, now=datetime.now(UTC)
            )
        )

    @router.post("/{ride_id}/walking-guidance")
    @permission_required(
        "arrival_waiting.rider.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def walking_guidance(
        ride_id: UUID, body: WalkingGuidanceRequest, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.walking_guidance(
                command(request), ride_id, body, now=datetime.now(UTC)
            )
        )

    return router
