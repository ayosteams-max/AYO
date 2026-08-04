from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.merchant_orders.application import MerchantOrderApplication
from BACKEND.merchant_orders.engine import MerchantOrderConflict
from BACKEND.merchant_orders.models import MerchantOrderAction


class MerchantDecisionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: MerchantOrderAction
    customer_reason_code: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]{2,62}$", max_length=63
    )
    customer_message: str | None = Field(default=None, max_length=240)
    internal_merchant_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def decision_shape(self) -> "MerchantDecisionCommand":
        if self.action is MerchantOrderAction.REJECT and (
            not self.customer_reason_code or not self.customer_message
        ):
            raise ValueError("rejection reason and customer message are required")
        if self.action is MerchantOrderAction.ACCEPT and any(
            (
                self.customer_reason_code,
                self.customer_message,
                self.internal_merchant_note,
            )
        ):
            raise ValueError("accept does not accept rejection fields")
        return self


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except MerchantOrderConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_merchant_order_router(application: MerchantOrderApplication) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/merchants/{merchant_id}/orders",
        tags=["merchant-orders"],
        route_class=AuthorizationRoute,
    )

    @router.get("")
    @permission_required(
        "merchant_orders.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def list_orders(
        merchant_id: UUID,
        request: Request,
        state: str | None = Query(default=None, max_length=63),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        return [
            value.model_dump(mode="json")
            for value in _call(
                lambda: application.list_orders(
                    _subject(request),
                    merchant_id=merchant_id,
                    state=state,
                    limit=limit,
                    at=datetime.now(UTC),
                )
            )
        ]

    @router.get("/{order_id}")
    @permission_required(
        "merchant_orders.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def detail(merchant_id: UUID, order_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.detail(
                _subject(request),
                merchant_id=merchant_id,
                order_id=order_id,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/{order_id}/decision")
    @permission_required(
        "merchant_orders.decide_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def decide(
        merchant_id: UUID,
        order_id: UUID,
        command: MerchantDecisionCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.decide(
                _subject(request),
                merchant_id=merchant_id,
                order_id=order_id,
                expected_version=command.expected_version,
                action=command.action,
                customer_reason_code=command.customer_reason_code,
                customer_message=command.customer_message,
                internal_merchant_note=command.internal_merchant_note,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    return router
