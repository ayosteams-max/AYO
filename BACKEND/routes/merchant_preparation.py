from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.merchant_preparation.application import MerchantPreparationApplication
from BACKEND.merchant_preparation.engine import PreparationConflict
from BACKEND.merchant_preparation.models import PreparationAction


class PreparationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: PreparationAction
    estimated_duration_minutes: int | None = Field(default=None, ge=1, le=240)
    progress_percent: int | None = Field(default=None, ge=1, le=99)
    delay_reason_code: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]{2,62}$", max_length=63
    )
    delay_message: str | None = Field(default=None, min_length=2, max_length=240)

    @model_validator(mode="after")
    def shape(self) -> "PreparationCommand":
        if (self.delay_reason_code is None) != (self.delay_message is None):
            raise ValueError("delay reason code and message must be provided together")
        if (
            self.action is PreparationAction.START
            and self.estimated_duration_minutes is None
        ):
            raise ValueError("start requires an estimate")
        if (
            self.action is PreparationAction.UPDATE_PROGRESS
            and self.progress_percent is None
        ):
            raise ValueError("progress update requires progress")
        if (
            self.action is not PreparationAction.START
            and self.estimated_duration_minutes is not None
        ):
            raise ValueError("estimate is start-only")
        if self.action is not PreparationAction.UPDATE_PROGRESS and any(
            (
                self.progress_percent is not None,
                self.delay_reason_code,
                self.delay_message,
            )
        ):
            raise ValueError("progress fields are update-only")
        return self


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except PreparationConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_merchant_preparation_router(
    application: MerchantPreparationApplication,
) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/merchants/{merchant_id}/orders/{order_id}/preparation",
        tags=["merchant-preparation"],
        route_class=AuthorizationRoute,
    )

    @router.get("")
    @permission_required(
        "merchant_preparation.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def detail(merchant_id: UUID, order_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.detail(
                _subject(request), merchant_id=merchant_id, order_id=order_id
            )
        ).model_dump(mode="json")

    @router.post("/actions")
    @permission_required(
        "merchant_preparation.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def command(
        merchant_id: UUID,
        order_id: UUID,
        command: PreparationCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.command(
                _subject(request),
                merchant_id=merchant_id,
                order_id=order_id,
                expected_version=command.expected_version,
                action=command.action,
                estimated_duration_minutes=command.estimated_duration_minutes,
                progress_percent=command.progress_percent,
                delay_reason_code=command.delay_reason_code,
                delay_message=command.delay_message,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    return router
