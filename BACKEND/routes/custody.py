from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.custody.application import CustodyApplication
from BACKEND.custody.engine import CustodyConflict
from BACKEND.custody.models import CustodyAction, VerificationMethod


class CustodyCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: CustodyAction
    code: str | None = Field(default=None, min_length=16, max_length=128)
    method: VerificationMethod | None = None


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except CustodyConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_custody_router(application: CustodyApplication) -> APIRouter:
    router = APIRouter(tags=["custody"], route_class=AuthorizationRoute)

    @router.get("/mobile/merchants/{merchant_id}/orders/{order_id}/custody")
    @permission_required(
        "custody.read_own_merchant",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def detail(merchant_id: UUID, order_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.merchant_detail(
                _subject(request), merchant_id=merchant_id, order_id=order_id
            )
        ).model_dump(mode="json")

    @router.post("/mobile/merchants/{merchant_id}/custody/{custody_id}/seal")
    @permission_required(
        "custody.release_own_merchant",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def seal(
        merchant_id: UUID,
        custody_id: UUID,
        command: CustodyCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        if command.action is not CustodyAction.SEAL:
            raise HTTPException(409, {"code": "seal_action_required"})
        return _call(
            lambda: application.seal(
                _subject(request),
                merchant_id=merchant_id,
                custody_id=custody_id,
                expected_version=command.expected_version,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/mobile/merchants/{merchant_id}/custody/{custody_id}/release")
    @permission_required(
        "custody.release_own_merchant",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def release(
        merchant_id: UUID,
        custody_id: UUID,
        command: CustodyCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.command(
                _subject(request),
                merchant_id=merchant_id,
                custody_id=custody_id,
                expected_version=command.expected_version,
                action=CustodyAction.RELEASE,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/mobile/custody/{custody_id}/actions")
    @permission_required(
        "custody.accept_assigned",
        resource_type="custody",
        resource_id_parameter="custody_id",
    )
    def courier(
        custody_id: UUID,
        command: CustodyCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        if command.action not in (CustodyAction.VERIFY, CustodyAction.ACCEPT):
            raise HTTPException(409, {"code": "courier_custody_action_required"})
        return _call(
            lambda: application.command(
                _subject(request),
                custody_id=custody_id,
                expected_version=command.expected_version,
                action=command.action,
                code=command.code,
                method=command.method,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    return router
