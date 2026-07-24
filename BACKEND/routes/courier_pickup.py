from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupExceptionReason,
)


class CourierPickupCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: CourierPickupAction
    reason: CourierPickupExceptionReason | None = None
    location_evidence_reference: UUID | None = None
    location_evidence_version: int | None = Field(default=None, ge=1)
    location_evidence_observed_at: datetime | None = None


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except CourierPickupConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_courier_pickup_router(application: CourierPickupApplication) -> APIRouter:
    router = APIRouter(tags=["courier-pickup"], route_class=AuthorizationRoute)

    @router.get("/mobile/merchants/{merchant_id}/orders/{order_id}/courier-pickup")
    @permission_required(
        "courier_pickup.read_own_merchant",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def merchant_detail(
        merchant_id: UUID, order_id: UUID, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.merchant_detail(
                _subject(request), merchant_id=merchant_id, order_id=order_id
            )
        ).model_dump(mode="json")

    @router.post(
        "/mobile/merchants/{merchant_id}/courier-pickups/{pickup_id}/acknowledge"
    )
    @permission_required(
        "courier_pickup.acknowledge_own_merchant",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def acknowledge(
        merchant_id: UUID,
        pickup_id: UUID,
        command: CourierPickupCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        if command.action not in {
            CourierPickupAction.ACKNOWLEDGE_ARRIVAL,
            CourierPickupAction.CORRECT_WAITING,
            CourierPickupAction.END_ATTEMPT,
        }:
            raise HTTPException(
                409, {"code": "merchant_acknowledgement_action_required"}
            )
        return _call(
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
        ).model_dump(mode="json")

    @router.get("/mobile/courier-pickups/{pickup_id}")
    @permission_required(
        "courier_pickup.manage_assigned",
        resource_type="courier_pickup",
        resource_id_parameter="pickup_id",
    )
    def courier_detail(pickup_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.courier_detail(_subject(request), pickup_id=pickup_id)
        ).model_dump(mode="json")

    @router.post("/mobile/courier-pickups/{pickup_id}/actions")
    @permission_required(
        "courier_pickup.manage_assigned",
        resource_type="courier_pickup",
        resource_id_parameter="pickup_id",
    )
    def courier_command(
        pickup_id: UUID,
        command: CourierPickupCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
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
        ).model_dump(mode="json")

    return router
