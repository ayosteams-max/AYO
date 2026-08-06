from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.custody.application import CustodyApplication
from BACKEND.custody.engine import CustodyConflict
from BACKEND.custody.models import (
    CustodyAction,
    CustodyState,
    CustodyStatusSnapshot,
    VerificationMethod,
)


class CustodyCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: CustodyAction
    code: str | None = Field(default=None, min_length=16, max_length=128)
    method: VerificationMethod | None = None


class MerchantCustodyRequiredAction(StrEnum):
    SEAL_ORDER = "seal_order"
    RELEASE_ORDER = "release_order"
    WAIT_FOR_COURIER = "wait_for_courier"
    HANDOFF_COMPLETE = "handoff_complete"
    NONE = "none"


class CourierCustodyRequiredAction(StrEnum):
    VERIFY_PICKUP = "verify_pickup"
    ACCEPT_CUSTODY = "accept_custody"
    WAIT_FOR_MERCHANT = "wait_for_merchant"
    HANDOFF_COMPLETE = "handoff_complete"
    NONE = "none"


class CustodyWaitingFor(StrEnum):
    MERCHANT = "merchant"
    COURIER = "courier"


class CustodyRecoveryCategory(StrEnum):
    VERIFICATION_EXPIRED = "verification_expired"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class MerchantCustodyStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    custody_id: UUID
    order_id: UUID
    state: CustodyState
    version: int = Field(ge=1)
    required_action: MerchantCustodyRequiredAction
    waiting_for: CustodyWaitingFor | None
    recovery: CustodyRecoveryCategory | None
    challenge_available: bool
    challenge_expires_at: datetime | None


class CourierCustodyStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: CustodyState
    version: int = Field(ge=1)
    required_action: CourierCustodyRequiredAction
    waiting_for: CustodyWaitingFor | None
    recovery: CustodyRecoveryCategory | None
    challenge_available: bool
    challenge_expires_at: datetime | None
    supported_verification_methods: tuple[VerificationMethod, ...]


class CourierCustodyNotStarted(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    availability: Literal["not_started"] = "not_started"


def _challenge_status(
    snapshot: CustodyStatusSnapshot, *, now: datetime
) -> tuple[bool, datetime | None, CustodyRecoveryCategory | None]:
    challenge = snapshot.challenge
    if snapshot.custody.state is not CustodyState.SEALED:
        return False, None, None
    if challenge is None or challenge.used_at is not None:
        return False, None, CustodyRecoveryCategory.TEMPORARILY_UNAVAILABLE
    if challenge.expires_at <= now:
        return (
            False,
            challenge.expires_at,
            CustodyRecoveryCategory.VERIFICATION_EXPIRED,
        )
    return True, challenge.expires_at, None


def _status_actions(
    state: CustodyState, *, challenge_available: bool
) -> tuple[
    MerchantCustodyRequiredAction,
    CourierCustodyRequiredAction,
    CustodyWaitingFor | None,
]:
    if state is CustodyState.WAITING:
        return (
            MerchantCustodyRequiredAction.SEAL_ORDER,
            CourierCustodyRequiredAction.WAIT_FOR_MERCHANT,
            CustodyWaitingFor.MERCHANT,
        )
    if state is CustodyState.SEALED:
        if not challenge_available:
            return (
                MerchantCustodyRequiredAction.NONE,
                CourierCustodyRequiredAction.NONE,
                None,
            )
        return (
            MerchantCustodyRequiredAction.WAIT_FOR_COURIER,
            CourierCustodyRequiredAction.VERIFY_PICKUP,
            CustodyWaitingFor.COURIER,
        )
    if state is CustodyState.VERIFIED:
        return (
            MerchantCustodyRequiredAction.RELEASE_ORDER,
            CourierCustodyRequiredAction.WAIT_FOR_MERCHANT,
            CustodyWaitingFor.MERCHANT,
        )
    if state is CustodyState.RELEASED:
        return (
            MerchantCustodyRequiredAction.WAIT_FOR_COURIER,
            CourierCustodyRequiredAction.ACCEPT_CUSTODY,
            CustodyWaitingFor.COURIER,
        )
    if state is CustodyState.ACCEPTED:
        return (
            MerchantCustodyRequiredAction.HANDOFF_COMPLETE,
            CourierCustodyRequiredAction.HANDOFF_COMPLETE,
            None,
        )
    raise RuntimeError("unsupported custody public state")


def _merchant_status(
    snapshot: CustodyStatusSnapshot, *, now: datetime
) -> MerchantCustodyStatus:
    available, expires_at, recovery = _challenge_status(snapshot, now=now)
    merchant_action, _, waiting_for = _status_actions(
        snapshot.custody.state, challenge_available=available
    )
    return MerchantCustodyStatus(
        custody_id=snapshot.custody.custody_id,
        order_id=snapshot.custody.order_id,
        state=snapshot.custody.state,
        version=snapshot.custody.version,
        required_action=merchant_action,
        waiting_for=waiting_for,
        recovery=recovery,
        challenge_available=available,
        challenge_expires_at=expires_at,
    )


def _courier_status(
    snapshot: CustodyStatusSnapshot, *, now: datetime
) -> CourierCustodyStatus:
    available, expires_at, recovery = _challenge_status(snapshot, now=now)
    _, courier_action, waiting_for = _status_actions(
        snapshot.custody.state, challenge_available=available
    )
    return CourierCustodyStatus(
        state=snapshot.custody.state,
        version=snapshot.custody.version,
        required_action=courier_action,
        waiting_for=waiting_for,
        recovery=recovery,
        challenge_available=available,
        challenge_expires_at=expires_at,
        supported_verification_methods=(tuple(VerificationMethod) if available else ()),
    )


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


def _status_call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except CustodyConflict as error:
        internal = str(error)
        if internal == "access_denied":
            raise HTTPException(403, {"code": "access_denied"}) from error
        if internal.endswith("not_found"):
            raise HTTPException(404, {"code": "custody_unavailable"}) from error
        raise HTTPException(503, {"code": "custody_temporarily_unavailable"}) from error


def create_custody_router(application: CustodyApplication) -> APIRouter:
    router = APIRouter(tags=["custody"], route_class=AuthorizationRoute)

    @router.get(
        "/mobile/merchants/{merchant_id}/orders/{order_id}/custody",
        response_model=MerchantCustodyStatus,
    )
    def detail(
        merchant_id: UUID, order_id: UUID, request: Request
    ) -> MerchantCustodyStatus:
        return _status_call(
            lambda: _merchant_status(
                application.merchant_detail(
                    _subject(request), merchant_id=merchant_id, order_id=order_id
                ),
                now=datetime.now(UTC),
            )
        )

    @router.get(
        "/mobile/courier-pickups/{pickup_id}/custody",
        response_model=CourierCustodyStatus | CourierCustodyNotStarted,
    )
    def courier_detail(
        pickup_id: UUID, request: Request
    ) -> CourierCustodyStatus | CourierCustodyNotStarted:
        snapshot = _status_call(
            lambda: application.courier_detail(_subject(request), pickup_id=pickup_id)
        )
        if snapshot is None:
            return CourierCustodyNotStarted()
        return _courier_status(snapshot, now=datetime.now(UTC))

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
