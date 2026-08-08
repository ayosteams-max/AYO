import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupExceptionReason,
    CourierPickupState,
    CourierPickupView,
)

logger = logging.getLogger(__name__)


class CourierPickupCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: CourierPickupAction
    reason: CourierPickupExceptionReason | None = None
    location_evidence_reference: UUID | None = None
    location_evidence_version: int | None = Field(default=None, ge=1)
    location_evidence_observed_at: datetime | None = None


class CourierPickupCourierCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_id: UUID
    state: CourierPickupState
    version: int
    assigned_at: datetime
    travelling_at: datetime | None
    arrived_at: datetime | None
    merchant_acknowledged_at: datetime | None
    waiting_duration_seconds: int | None
    terminal_reason: CourierPickupExceptionReason | None
    updated_at: datetime


class CourierPickupPresentationAction(StrEnum):
    START_TRAVEL = "start_travel"
    MARK_ARRIVED = "mark_arrived"
    NONE = "none"


class CourierPickupMerchantPresentationAction(StrEnum):
    ACKNOWLEDGE_ARRIVAL = "acknowledge_arrival"
    NONE = "none"


PRESENTATION_ACTION_BY_STATE = {
    CourierPickupState.ASSIGNED: CourierPickupPresentationAction.START_TRAVEL,
    CourierPickupState.TRAVELLING: CourierPickupPresentationAction.MARK_ARRIVED,
    CourierPickupState.ARRIVED: CourierPickupPresentationAction.NONE,
    CourierPickupState.WAITING: CourierPickupPresentationAction.NONE,
    CourierPickupState.ENDED_BEFORE_CUSTODY: CourierPickupPresentationAction.NONE,
}

MERCHANT_PRESENTATION_ACTION_BY_STATE = {
    CourierPickupState.ASSIGNED: CourierPickupMerchantPresentationAction.NONE,
    CourierPickupState.TRAVELLING: CourierPickupMerchantPresentationAction.NONE,
    CourierPickupState.ARRIVED: (
        CourierPickupMerchantPresentationAction.ACKNOWLEDGE_ARRIVAL
    ),
    CourierPickupState.WAITING: CourierPickupMerchantPresentationAction.NONE,
    CourierPickupState.ENDED_BEFORE_CUSTODY: (
        CourierPickupMerchantPresentationAction.NONE
    ),
}

if set(MERCHANT_PRESENTATION_ACTION_BY_STATE) != set(CourierPickupState):
    raise RuntimeError("merchant courier pickup presentation matrix is incomplete")


class CourierPickupCourierStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_id: UUID
    state: CourierPickupState
    version: int
    assigned_at: datetime
    travelling_at: datetime | None
    arrived_at: datetime | None
    merchant_acknowledged_at: datetime | None
    waiting_duration_seconds: int | None
    terminal_reason: CourierPickupExceptionReason | None
    updated_at: datetime
    presentation_action: CourierPickupPresentationAction


class CourierPickupMerchantStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_id: UUID
    state: CourierPickupState
    version: int
    arrived_at: datetime | None
    merchant_acknowledged_at: datetime | None
    waiting_duration_seconds: int | None
    terminal_reason: CourierPickupExceptionReason | None
    updated_at: datetime
    presentation_action: CourierPickupMerchantPresentationAction


class CourierPickupMerchantCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_id: UUID
    state: CourierPickupState
    version: int
    arrived_at: datetime | None
    merchant_acknowledged_at: datetime | None
    waiting_duration_seconds: int | None
    terminal_reason: CourierPickupExceptionReason | None
    updated_at: datetime


def _courier_command_result(
    view: CourierPickupView,
) -> CourierPickupCourierCommandResult:
    pickup = view.pickup
    return CourierPickupCourierCommandResult(
        pickup_id=pickup.pickup_id,
        state=pickup.state,
        version=pickup.version,
        assigned_at=pickup.assigned_at,
        travelling_at=pickup.travelling_at,
        arrived_at=pickup.arrived_at,
        merchant_acknowledged_at=pickup.merchant_acknowledged_at,
        waiting_duration_seconds=pickup.waiting_duration_seconds,
        terminal_reason=pickup.terminal_reason,
        updated_at=pickup.updated_at,
    )


def _courier_status(view: CourierPickupView) -> CourierPickupCourierStatus:
    pickup = view.pickup
    return CourierPickupCourierStatus(
        pickup_id=pickup.pickup_id,
        state=pickup.state,
        version=pickup.version,
        assigned_at=pickup.assigned_at,
        travelling_at=pickup.travelling_at,
        arrived_at=pickup.arrived_at,
        merchant_acknowledged_at=pickup.merchant_acknowledged_at,
        waiting_duration_seconds=pickup.waiting_duration_seconds,
        terminal_reason=pickup.terminal_reason,
        updated_at=pickup.updated_at,
        presentation_action=PRESENTATION_ACTION_BY_STATE[pickup.state],
    )


def _merchant_status(view: CourierPickupView) -> CourierPickupMerchantStatus:
    pickup = view.pickup
    return CourierPickupMerchantStatus(
        pickup_id=pickup.pickup_id,
        state=pickup.state,
        version=pickup.version,
        arrived_at=pickup.arrived_at,
        merchant_acknowledged_at=pickup.merchant_acknowledged_at,
        waiting_duration_seconds=pickup.waiting_duration_seconds,
        terminal_reason=pickup.terminal_reason,
        updated_at=pickup.updated_at,
        presentation_action=MERCHANT_PRESENTATION_ACTION_BY_STATE[pickup.state],
    )


def _merchant_command_result(
    view: CourierPickupView,
) -> CourierPickupMerchantCommandResult:
    pickup = view.pickup
    return CourierPickupMerchantCommandResult(
        pickup_id=pickup.pickup_id,
        state=pickup.state,
        version=pickup.version,
        arrived_at=pickup.arrived_at,
        merchant_acknowledged_at=pickup.merchant_acknowledged_at,
        waiting_duration_seconds=pickup.waiting_duration_seconds,
        terminal_reason=pickup.terminal_reason,
        updated_at=pickup.updated_at,
    )


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except CourierPickupConflict as error:
        internal_code = str(error)
        public = {
            "access_denied": (403, "access_denied"),
            "courier_pickup_not_found": (404, "courier_pickup_unavailable"),
            "courier_pickup_unavailable": (404, "courier_pickup_unavailable"),
            "idempotency_conflict": (409, "idempotency_conflict"),
            "courier_pickup_version_conflict": (
                409,
                "courier_pickup_version_conflict",
            ),
            "invalid_courier_pickup_transition": (
                409,
                "courier_pickup_transition_not_allowed",
            ),
            "location_evidence_invalid": (
                409,
                "location_evidence_stale_or_invalid",
            ),
            "location_evidence_stale_or_invalid": (
                409,
                "location_evidence_stale_or_invalid",
            ),
            "idempotency_record_incompatible": (
                409,
                "idempotency_replay_unavailable",
            ),
            "merchant_acknowledgement_required": (
                409,
                "courier_pickup_transition_not_allowed",
            ),
            "merchant_acknowledgement_action_required": (
                409,
                "courier_pickup_transition_not_allowed",
            ),
            "pickup_end_reason_not_permitted": (
                409,
                "courier_pickup_transition_not_allowed",
            ),
            "pickup_end_reason_required": (
                409,
                "courier_pickup_transition_not_allowed",
            ),
            "pickup_authority_ended_at_custody": (
                409,
                "courier_pickup_transition_not_allowed",
            ),
            "courier_pickup_assignment_invalid": (
                409,
                "courier_pickup_temporarily_unavailable",
            ),
            "merchant_unavailable": (
                409,
                "courier_pickup_temporarily_unavailable",
            ),
            "courier_pickup_custody_activation_conflict": (
                409,
                "courier_pickup_temporarily_unavailable",
            ),
        }.get(internal_code)
        if public is None:
            logger.error("unclassified courier pickup conflict")
            raise HTTPException(500, {"code": "request_rejected"}) from error
        status, public_code = public
        raise HTTPException(status, {"code": public_code}) from error


def create_courier_pickup_router(application: CourierPickupApplication) -> APIRouter:
    router = APIRouter(tags=["courier-pickup"], route_class=AuthorizationRoute)

    @router.get(
        "/mobile/merchants/{merchant_id}/orders/{order_id}/courier-pickup",
        response_model=CourierPickupMerchantStatus,
    )
    def merchant_detail(
        merchant_id: UUID, order_id: UUID, request: Request
    ) -> CourierPickupMerchantStatus:
        return _merchant_status(
            _call(
                lambda: application.merchant_detail(
                    _subject(request), merchant_id=merchant_id, order_id=order_id
                )
            )
        )

    @router.post(
        "/mobile/merchants/{merchant_id}/courier-pickups/{pickup_id}/acknowledge",
        response_model=CourierPickupMerchantCommandResult,
    )
    def acknowledge(
        merchant_id: UUID,
        pickup_id: UUID,
        command: CourierPickupCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> CourierPickupMerchantCommandResult:
        if command.action not in {
            CourierPickupAction.ACKNOWLEDGE_ARRIVAL,
            CourierPickupAction.CORRECT_WAITING,
            CourierPickupAction.END_ATTEMPT,
        }:
            raise HTTPException(409, {"code": "courier_pickup_transition_not_allowed"})
        return _merchant_command_result(
            _call(
                lambda: application.merchant_acknowledge(
                    _subject(request),
                    merchant_id=merchant_id,
                    pickup_id=pickup_id,
                    expected_version=command.expected_version,
                    idempotency_key=idempotency_key,
                    at=datetime.now(UTC),
                    action=command.action,
                    reason=command.reason,
                )
            )
        )

    @router.get(
        "/mobile/courier-pickups/{pickup_id}",
        response_model=CourierPickupCourierStatus,
    )
    def courier_detail(pickup_id: UUID, request: Request) -> CourierPickupCourierStatus:
        return _courier_status(
            _call(
                lambda: application.courier_detail(
                    _subject(request), pickup_id=pickup_id
                )
            )
        )

    @router.post(
        "/mobile/courier-pickups/{pickup_id}/actions",
        response_model=CourierPickupCourierCommandResult,
    )
    def courier_command(
        pickup_id: UUID,
        command: CourierPickupCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> CourierPickupCourierCommandResult:
        return _courier_command_result(
            _call(
                lambda: application.courier_command(
                    _subject(request),
                    pickup_id=pickup_id,
                    expected_version=command.expected_version,
                    action=command.action,
                    idempotency_key=idempotency_key,
                    at=datetime.now(UTC),
                    reason=command.reason,
                    location_evidence_reference=command.location_evidence_reference,
                    location_evidence_version=command.location_evidence_version,
                    location_evidence_observed_at=command.location_evidence_observed_at,
                )
            )
        )

    return router
