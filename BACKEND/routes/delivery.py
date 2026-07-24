from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.delivery_verification.application import DeliveryApplication
from BACKEND.delivery_verification.engine import DeliveryConflict
from BACKEND.delivery_verification.models import (
    DeliveryAction,
    DeliveryVerificationMethod,
)


class DeliveryCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: DeliveryAction
    code: str | None = Field(default=None, min_length=8, max_length=64)
    method: DeliveryVerificationMethod | None = None


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except DeliveryConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_delivery_router(application: DeliveryApplication) -> APIRouter:
    router = APIRouter(tags=["delivery-verification"], route_class=AuthorizationRoute)

    @router.get("/mobile/orders/{order_id}/delivery-credential")
    @permission_required(
        "delivery.read_own", resource_type="order", resource_id_parameter="order_id"
    )
    def credential(order_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.credential(_subject(request), order_id=order_id)
        ).model_dump(mode="json")

    @router.post("/mobile/deliveries/{delivery_id}/courier-actions")
    @permission_required(
        "delivery.manage_assigned",
        resource_type="delivery",
        resource_id_parameter="delivery_id",
    )
    def courier(
        delivery_id: UUID,
        command: DeliveryCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.command(
                _subject(request),
                delivery_id=delivery_id,
                expected_version=command.expected_version,
                action=command.action,
                code=command.code,
                method=command.method,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/mobile/deliveries/{delivery_id}/customer-received")
    @permission_required(
        "delivery.confirm_receipt",
        resource_type="delivery",
        resource_id_parameter="delivery_id",
    )
    def received(
        delivery_id: UUID,
        command: DeliveryCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        if command.action is not DeliveryAction.CONFIRM_RECEIVED:
            raise HTTPException(409, {"code": "customer_received_action_required"})
        return _call(
            lambda: application.customer_received(
                _subject(request),
                delivery_id=delivery_id,
                expected_version=command.expected_version,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    return router
