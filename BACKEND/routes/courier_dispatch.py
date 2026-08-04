from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.courier_dispatch.application import CourierDispatchApplication
from BACKEND.courier_dispatch.engine import CourierDispatchConflict
from BACKEND.courier_dispatch.models import CourierDispatchAction


class CourierDispatchCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: CourierDispatchAction

    @property
    def courier_action(self) -> CourierDispatchAction:
        if self.action not in {
            CourierDispatchAction.ACCEPT,
            CourierDispatchAction.DECLINE,
        }:
            raise CourierDispatchConflict("offer_requires_dispatch_authority")
        return self.action


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except CourierDispatchConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_courier_dispatch_router(
    application: CourierDispatchApplication,
) -> APIRouter:
    router = APIRouter(tags=["courier-dispatch"], route_class=AuthorizationRoute)

    @router.get("/mobile/merchants/{merchant_id}/orders/{order_id}/courier-dispatch")
    @permission_required(
        "courier_dispatch.read_own_merchant",
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

    @router.post("/mobile/courier-dispatch/{dispatch_id}/actions")
    @permission_required(
        "courier_dispatch.respond_offer",
        resource_type="courier_dispatch",
        resource_id_parameter="dispatch_id",
    )
    def command(
        dispatch_id: UUID,
        command: CourierDispatchCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        subject = _subject(request)
        return _call(
            lambda: application.command(
                subject,
                dispatch_id=dispatch_id,
                expected_version=command.expected_version,
                action=command.courier_action,
                courier_identity_id=subject.identity_id,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    return router
