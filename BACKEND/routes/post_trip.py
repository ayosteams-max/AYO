from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.post_trip.application import PostTripApplication
from BACKEND.post_trip.engine import PostTripConflict


class CashCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    confirmed: bool


class RatingCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stars: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=1000)
    prefer_driver: bool = False


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except PostTripConflict as error:
        code = str(error)
        status = (
            404
            if code.endswith("not_found")
            else 403
            if code == "access_denied"
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_post_trip_router(application: PostTripApplication) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/post-trip", tags=["post-trip"], route_class=AuthorizationRoute
    )

    @router.get("/{ride_id}")
    @permission_required(
        "post_trip.read_own",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def summary(ride_id: UUID, request: Request) -> dict[str, Any]:
        return _call(lambda: application.summary(_subject(request), ride_id=ride_id))

    @router.post("/{ride_id}/cash-confirmation")
    @permission_required(
        "post_trip.cash.confirm",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def cash(
        ride_id: UUID,
        command: CashCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        result = _call(
            lambda: application.confirm_cash(
                _subject(request),
                ride_id=ride_id,
                confirmed=command.confirmed,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        )
        return result.model_dump(mode="json")

    @router.post("/{ride_id}/ratings", status_code=201)
    @permission_required(
        "post_trip.rating.create",
        resource_type="active_ride",
        resource_id_parameter="ride_id",
    )
    def rating(
        ride_id: UUID, command: RatingCommand, request: Request
    ) -> dict[str, Any]:
        result = _call(
            lambda: application.rate(
                _subject(request),
                ride_id=ride_id,
                stars=command.stars,
                feedback=command.feedback,
                prefer_driver=command.prefer_driver,
                at=datetime.now(UTC),
            )
        )
        return result.model_dump(mode="json")

    return router
