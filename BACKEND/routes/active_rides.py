from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from BACKEND.active_ride.application import (
    AckCommand,
    ActiveRideApplication,
    CommandEnvelope,
    EvidenceCommand,
    PickupChangeCommand,
    PickupVerifyCommand,
    ProgressCommand,
    RequestPickupVerificationCommand,
)
from BACKEND.active_ride.engine import ActiveRideConflict
from BACKEND.active_ride.models import ActiveRideState
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
    except ActiveRideConflict as error:
        code = str(error).split(":", 1)[0]
        status = (
            404 if code == "ride_not_found" else 403 if code == "access_denied" else 409
        )
        public = (
            code
            if code
            in {
                "ride_not_found",
                "access_denied",
                "stale_command",
                "idempotency_conflict",
                "verification_failed",
                "verification_expired",
                "verification_cooldown",
                "verification_locked",
                "pickup_change_not_pending",
                "invalid_acknowledgement",
                "resync_required",
            }
            else "ride_state_conflict"
        )
        raise HTTPException(status, {"code": public}) from error


def create_active_ride_router(application: ActiveRideApplication) -> APIRouter:
    router = APIRouter(
        prefix="/active-rides", tags=["active-rides"], route_class=AuthorizationRoute
    )

    def read_limit(request: Request, subject: AuthorizationSubject) -> None:
        require_rate_limit(request, subject, "active_ride_read")

    def command_limit(request: Request, subject: AuthorizationSubject) -> None:
        require_rate_limit(request, subject, "active_ride_command")

    @router.get("/{ride_id}")
    @permission_required(
        "active_ride.read", resource_type="active_ride", resource_id_parameter="ride_id"
    )
    def snapshot(ride_id: UUID, request: Request) -> dict[str, Any]:
        subject = _subject(request)
        read_limit(request, subject)
        return _call(lambda: application.snapshot(subject, ride_id))

    @router.get("/{ride_id}/events")
    @permission_required(
        "active_ride.read", resource_type="active_ride", resource_id_parameter="ride_id"
    )
    def events(
        ride_id: UUID,
        request: Request,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, Any]:
        subject = _subject(request)
        read_limit(request, subject)
        return {
            "events": _call(
                lambda: application.events(subject, ride_id, after=after, limit=limit)
            ),
            "poll_after_seconds": 2,
        }

    @router.post("/{ride_id}/acks", status_code=204)
    @permission_required(
        "active_ride.read", resource_type="active_ride", resource_id_parameter="ride_id"
    )
    def acknowledge(ride_id: UUID, command: AckCommand, request: Request) -> None:
        subject = _subject(request)
        command_limit(request, subject)
        _call(
            lambda: application.acknowledge(
                subject, ride_id, command.sequence, now=datetime.now(UTC)
            )
        )

    def execute(
        ride_id: UUID,
        command: CommandEnvelope,
        request: Request,
        event: str,
        target: ActiveRideState,
        driver_only: bool = False,
    ) -> dict[str, Any]:
        subject = _subject(request)
        command_limit(request, subject)
        return _call(
            lambda: application.command(
                subject,
                ride_id,
                command,
                command_type=event,
                target=target,
                driver_only=driver_only,
                now=datetime.now(UTC),
            )
        )

    @router.post("/{ride_id}/driver/en-route")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def en_route(
        ride_id: UUID, command: CommandEnvelope, request: Request
    ) -> dict[str, Any]:
        return execute(
            ride_id,
            command,
            request,
            "driver_en_route",
            ActiveRideState.DRIVER_EN_ROUTE,
            True,
        )

    @router.post("/{ride_id}/driver/arrived")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def arrived(
        ride_id: UUID, command: CommandEnvelope, request: Request
    ) -> dict[str, Any]:
        return execute(
            ride_id,
            command,
            request,
            "driver_arrived",
            ActiveRideState.DRIVER_ARRIVED,
            True,
        )

    @router.post("/{ride_id}/pickup-verification/request")
    @permission_required("active_ride.rider.command", resource_type="active_ride")
    def request_verification(
        ride_id: UUID, command: RequestPickupVerificationCommand, request: Request
    ) -> dict[str, str]:
        subject = _subject(request)
        require_rate_limit(request, subject, "active_ride_verification")
        return _call(
            lambda: application.issue_verification(
                subject, ride_id, command, now=datetime.now(UTC)
            )
        )

    @router.post("/{ride_id}/pickup-verification/verify")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def verify(
        ride_id: UUID, command: PickupVerifyCommand, request: Request
    ) -> dict[str, Any]:
        subject = _subject(request)
        require_rate_limit(request, subject, "active_ride_verification")
        return _call(
            lambda: application.verify_pickup(
                subject, ride_id, command, now=datetime.now(UTC)
            )
        )

    @router.post("/{ride_id}/start")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def start(
        ride_id: UUID, command: CommandEnvelope, request: Request
    ) -> dict[str, Any]:
        return execute(
            ride_id, command, request, "trip_started", ActiveRideState.IN_PROGRESS, True
        )

    @router.post("/{ride_id}/progress")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def progress(
        ride_id: UUID, command: ProgressCommand, request: Request
    ) -> dict[str, Any]:
        if command.progress_basis_points < 9000:
            return execute(
                ride_id,
                command,
                request,
                "trip_progress_updated",
                ActiveRideState.IN_PROGRESS,
                True,
            )
        return execute(
            ride_id,
            command,
            request,
            "destination_approaching",
            ActiveRideState.DESTINATION_APPROACHING,
            True,
        )

    @router.post("/{ride_id}/destination-approaching")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def approaching(
        ride_id: UUID, command: CommandEnvelope, request: Request
    ) -> dict[str, Any]:
        return execute(
            ride_id,
            command,
            request,
            "destination_approaching",
            ActiveRideState.DESTINATION_APPROACHING,
            True,
        )

    @router.post("/{ride_id}/completion/request")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def request_completion(
        ride_id: UUID, command: CommandEnvelope, request: Request
    ) -> dict[str, Any]:
        return execute(
            ride_id,
            command,
            request,
            "completion_requested",
            ActiveRideState.COMPLETION_PENDING,
            True,
        )

    @router.post("/{ride_id}/complete")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def complete(
        ride_id: UUID, command: CommandEnvelope, request: Request
    ) -> dict[str, Any]:
        return execute(
            ride_id, command, request, "trip_completed", ActiveRideState.COMPLETED, True
        )

    @router.post("/{ride_id}/rider-cancellation")
    @permission_required("active_ride.rider.command", resource_type="active_ride")
    def rider_cancel(
        ride_id: UUID, command: EvidenceCommand, request: Request
    ) -> dict[str, Any]:
        subject = _subject(request)
        command_limit(request, subject)
        return _call(
            lambda: application.evidence_transition(
                subject,
                ride_id,
                command,
                command_type="rider_cancellation_requested",
                target=ActiveRideState.CANCELLATION_PENDING,
                driver_only=False,
                now=datetime.now(UTC),
            )
        )

    @router.post("/{ride_id}/driver-cancellation")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def driver_cancel(
        ride_id: UUID, command: EvidenceCommand, request: Request
    ) -> dict[str, Any]:
        subject = _subject(request)
        command_limit(request, subject)
        return _call(
            lambda: application.evidence_transition(
                subject,
                ride_id,
                command,
                command_type="driver_cancellation_requested",
                target=ActiveRideState.REASSIGNING,
                driver_only=True,
                now=datetime.now(UTC),
            )
        )

    @router.post("/{ride_id}/no-show")
    @permission_required("active_ride.driver.command", resource_type="active_ride")
    def no_show(
        ride_id: UUID, command: EvidenceCommand, request: Request
    ) -> dict[str, Any]:
        subject = _subject(request)
        command_limit(request, subject)
        return _call(
            lambda: application.evidence_transition(
                subject,
                ride_id,
                command,
                command_type="no_show_review_started",
                target=ActiveRideState.NO_SHOW_REVIEW,
                driver_only=True,
                now=datetime.now(UTC),
            )
        )

    @router.post("/{ride_id}/recovery")
    @permission_required("active_ride.rider.command", resource_type="active_ride")
    def recovery(
        ride_id: UUID, command: EvidenceCommand, request: Request
    ) -> dict[str, Any]:
        subject = _subject(request)
        command_limit(request, subject)
        return _call(
            lambda: application.evidence_transition(
                subject,
                ride_id,
                command,
                command_type="recovery_requested",
                target=ActiveRideState.OPERATIONAL_RECOVERY,
                driver_only=False,
                now=datetime.now(UTC),
            )
        )

    @router.get("/{ride_id}/confidence")
    @permission_required("active_ride.read", resource_type="active_ride")
    def confidence(ride_id: UUID, request: Request) -> dict[str, Any]:
        result = _call(lambda: application.confidence(_subject(request), ride_id))
        return {
            "confidence": None if result is None else result.model_dump(mode="json")
        }

    @router.get("/{ride_id}/pickup-recommendation")
    @permission_required("active_ride.read", resource_type="active_ride")
    def pickup(ride_id: UUID, request: Request) -> dict[str, Any]:
        result = _call(lambda: application.pickup(_subject(request), ride_id))
        return {
            "pickup_recommendation": None
            if result is None
            else result.model_dump(mode="json")
        }

    @router.post("/{ride_id}/pickup-recommendation/respond")
    @permission_required("active_ride.rider.command", resource_type="active_ride")
    def pickup_response(
        ride_id: UUID, command: PickupChangeCommand, request: Request
    ) -> dict[str, Any]:
        result = _call(
            lambda: application.pickup_change(_subject(request), ride_id, command)
        )
        return result.model_dump(mode="json")

    return router
