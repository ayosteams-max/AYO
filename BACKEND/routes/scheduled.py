from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.dispatch.api_security import require_rate_limit
from BACKEND.scheduled.engine import ReservationConflict
from BACKEND.scheduled.integration import ScheduledIntegrationApplication
from BACKEND.scheduled.integration_models import (
    CreateScheduledReservationCommand,
    DriverCommitmentResponseCommand,
    PickupVerificationCommand,
    PublicReservation,
    UpdateReservationCommand,
)


def _subject(request: Request) -> AuthorizationSubject:
    subject: AuthorizationSubject | None = getattr(
        request.state, "authorization_subject", None
    )
    if subject is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return subject


def _call(operation):
    try:
        return operation()
    except ReservationConflict as error:
        message = str(error)
        if "Step-up" in message:
            code, http_status = (
                "step_up_required",
                status.HTTP_428_PRECONDITION_REQUIRED,
            )
        elif "ownership" in message or "authorized" in message:
            code, http_status = "access_denied", status.HTTP_403_FORBIDDEN
        elif "not found" in message:
            code, http_status = "reservation_not_found", status.HTTP_404_NOT_FOUND
        else:
            code, http_status = "reservation_conflict", status.HTTP_409_CONFLICT
        raise HTTPException(http_status, {"code": code}) from error


def create_scheduled_router(application: ScheduledIntegrationApplication) -> APIRouter:
    router = APIRouter(
        prefix="/scheduled",
        tags=["scheduled"],
        route_class=AuthorizationRoute,
    )

    @router.post("/reservations", response_model=PublicReservation, status_code=201)
    @permission_required("scheduled.rider.create", resource_type="reservation")
    def create_reservation(
        command: CreateScheduledReservationCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> PublicReservation:
        subject = _subject(request)
        require_rate_limit(request, subject, "scheduled_create")
        result, _ = _call(
            lambda: application.create(
                subject,
                command,
                idempotency_key=idempotency_key,
                now=datetime.now(UTC),
            )
        )
        return result

    @router.get("/reservations/{reservation_id}", response_model=PublicReservation)
    @permission_required(
        "scheduled.reservation.read",
        resource_type="reservation",
        resource_id_parameter="reservation_id",
    )
    def read_reservation(reservation_id: UUID, request: Request) -> PublicReservation:
        return _call(lambda: application.read(_subject(request), reservation_id))

    @router.get(
        "/reservations/{reservation_id}/status", response_model=PublicReservation
    )
    @permission_required(
        "scheduled.reservation.read",
        resource_type="reservation",
        resource_id_parameter="reservation_id",
    )
    def reservation_status(reservation_id: UUID, request: Request) -> PublicReservation:
        return _call(lambda: application.read(_subject(request), reservation_id))

    @router.patch("/reservations/{reservation_id}", response_model=PublicReservation)
    @permission_required(
        "scheduled.reservation.manage",
        resource_type="reservation",
        resource_id_parameter="reservation_id",
    )
    def update_reservation(
        reservation_id: UUID, command: UpdateReservationCommand, request: Request
    ) -> PublicReservation:
        subject = _subject(request)
        require_rate_limit(request, subject, "scheduled_manage")
        return _call(
            lambda: application.update(
                subject, reservation_id, command, now=datetime.now(UTC)
            )
        )

    @router.post(
        "/reservations/{reservation_id}/cancel", response_model=PublicReservation
    )
    @permission_required(
        "scheduled.reservation.manage",
        resource_type="reservation",
        resource_id_parameter="reservation_id",
    )
    def cancel_reservation(reservation_id: UUID, request: Request) -> PublicReservation:
        return _call(
            lambda: application.cancel(
                _subject(request), reservation_id, now=datetime.now(UTC)
            )
        )

    @router.post(
        "/reservations/{reservation_id}/passenger/confirm",
        response_model=PublicReservation,
    )
    @permission_required("scheduled.reservation.manage", resource_type="reservation")
    def confirm_passenger(reservation_id: UUID, request: Request) -> PublicReservation:
        subject = _subject(request)
        require_rate_limit(request, subject, "scheduled_confirmation")
        return _call(
            lambda: application.confirm_or_decline(
                subject, reservation_id, confirmed=True, now=datetime.now(UTC)
            )
        )

    @router.post(
        "/reservations/{reservation_id}/passenger/decline",
        response_model=PublicReservation,
    )
    @permission_required("scheduled.reservation.manage", resource_type="reservation")
    def decline_passenger(reservation_id: UUID, request: Request) -> PublicReservation:
        subject = _subject(request)
        require_rate_limit(request, subject, "scheduled_confirmation")
        return _call(
            lambda: application.confirm_or_decline(
                subject,
                reservation_id,
                confirmed=False,
                now=datetime.now(UTC),
            )
        )

    @router.post(
        "/reservations/{reservation_id}/driver/commitment",
        response_model=PublicReservation,
    )
    @permission_required(
        "scheduled.driver.commitment.respond", resource_type="reservation"
    )
    def driver_commitment(
        reservation_id: UUID,
        command: DriverCommitmentResponseCommand,
        request: Request,
    ) -> PublicReservation:
        return _call(
            lambda: application.driver_commitment_response(
                _subject(request),
                reservation_id,
                accepted=command.accepted,
                expected_version=command.expected_version,
                now=datetime.now(UTC),
            )
        )

    @router.post(
        "/reservations/{reservation_id}/driver/en-route",
        response_model=PublicReservation,
    )
    @permission_required(
        "scheduled.driver.commitment.respond", resource_type="reservation"
    )
    def driver_en_route(reservation_id: UUID, request: Request) -> PublicReservation:
        return _call(
            lambda: application.driver_progress(
                _subject(request), reservation_id, ready=False, now=datetime.now(UTC)
            )
        )

    @router.post(
        "/reservations/{reservation_id}/driver/ready", response_model=PublicReservation
    )
    @permission_required(
        "scheduled.driver.commitment.respond", resource_type="reservation"
    )
    def driver_ready(reservation_id: UUID, request: Request) -> PublicReservation:
        return _call(
            lambda: application.driver_progress(
                _subject(request), reservation_id, ready=True, now=datetime.now(UTC)
            )
        )

    @router.post(
        "/reservations/{reservation_id}/pickup/verify", response_model=PublicReservation
    )
    @permission_required(
        "scheduled.driver.commitment.respond", resource_type="reservation"
    )
    def verify_pickup(
        reservation_id: UUID, command: PickupVerificationCommand, request: Request
    ) -> PublicReservation:
        return _call(
            lambda: application.verify_pickup(
                _subject(request), reservation_id, command.code, now=datetime.now(UTC)
            )
        )

    @router.post(
        "/reservations/{reservation_id}/support-handoff",
        response_model=PublicReservation,
    )
    @permission_required("scheduled.support.handoff", resource_type="reservation")
    def support_handoff(reservation_id: UUID, request: Request) -> PublicReservation:
        return _call(
            lambda: application.support_handoff(
                _subject(request), reservation_id, now=datetime.now(UTC)
            )
        )

    return router
