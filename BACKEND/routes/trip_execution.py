from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from BACKEND.active_ride.engine import ActiveRideConflict
from BACKEND.active_ride.lifecycle import (
    ActiveRideLifecycleApplication,
    LifecycleCommand,
)
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.dispatch.api_security import require_rate_limit


def _subject(request: Request) -> AuthorizationSubject:
    subject = getattr(request.state, "authorization_subject", None)
    if subject is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return subject


def create_trip_execution_router(
    application: ActiveRideLifecycleApplication,
) -> APIRouter:
    """Canonical Milestone 6 API. It exposes no financial or settlement command."""
    router = APIRouter(
        prefix="/mobile/trips", tags=["trip-execution"], route_class=AuthorizationRoute
    )

    @router.get("/metadata/states")
    def states() -> dict[str, object]:
        return {
            "canonical_states": [
                "driver_assigned",
                "driver_en_route",
                "driver_arrived",
                "pickup_confirmed",
                "ride_in_progress",
                "destination_arrived",
                "completed",
            ],
            "financial_settlement_started": False,
            "sos_operational": False,
        }

    @router.get("/{ride_id}")
    @permission_required(
        "active_ride.read", resource_type="active_ride", resource_id_parameter="ride_id"
    )
    def recover(
        ride_id: UUID, request: Request, after_sequence: int = 0
    ) -> dict[str, object]:
        subject = _subject(request)
        require_rate_limit(request, subject, "active_ride_read")
        try:
            return application.recover(subject, ride_id, after_sequence=after_sequence)
        except ActiveRideConflict as error:
            code = str(error).split(":", 1)[0]
            status = (
                404
                if code == "ride_not_found"
                else 403
                if code == "access_denied"
                else 409
            )
            raise HTTPException(
                status,
                {
                    "code": code
                    if code in {"ride_not_found", "access_denied", "resync_required"}
                    else "trip_state_conflict"
                },
            ) from error

    @router.post("/{ride_id}/commands")
    @permission_required(
        "active_ride.driver.command",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def command(
        ride_id: UUID, item: LifecycleCommand, request: Request
    ) -> dict[str, object]:
        subject = _subject(request)
        require_rate_limit(request, subject, "active_ride_command")
        try:
            return application.command(subject, ride_id, item, now=datetime.now(UTC))
        except ActiveRideConflict as error:
            code = str(error).split(":", 1)[0]
            status = (
                404
                if code == "ride_not_found"
                else 403
                if code == "access_denied"
                else 409
            )
            public = (
                code
                if code
                in {
                    "ride_not_found",
                    "access_denied",
                    "stale_command",
                    "idempotency_conflict",
                }
                else "trip_state_conflict"
            )
            raise HTTPException(status, {"code": public}) from error

    return router
