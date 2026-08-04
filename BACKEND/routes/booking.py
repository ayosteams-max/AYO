from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import (
    AuthorizationRoute,
    TrustedSubjectResolver,
    permission_required,
)
from BACKEND.booking.application import (
    BookingApplication,
    ConfirmBookingCommand,
    PreviewRouteCommand,
)
from BACKEND.booking.models import BookingConflict, PlaceCandidate, TollEvidenceState
from BACKEND.ride_request.models import DestinationDefinition, PickupDefinition


class RoutePreviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    client_preview_id: UUID
    booking_session: str = Field(
        min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    pickup: PickupDefinition
    destination: DestinationDefinition
    service_type: str = Field(pattern=r"^immediate_standard$")


class RoutePreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID
    evidence_hash: str
    pickup: str
    destination: str
    geometry: tuple[tuple[float, float], ...]
    distance_metres: int
    duration_seconds: int
    traffic_state: str
    toll_state: str
    toll_amount_minor: int | None
    toll_message: str | None
    quote_id: UUID
    currency: str
    estimated_fare_minor: int
    pricing_version: str
    fare_explanation: tuple[str, ...]
    surge_applied: bool
    expires_at: datetime
    attribution: str


class ConfirmBookingRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_id: UUID
    booking_session: str = Field(
        min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    client_request_id: UUID
    consent_policy_version: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")


class ConfirmBookingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    confirmation_id: UUID
    ride_request_id: UUID
    state: str
    dispatch_started: bool = False
    next_step: str = "waiting_for_driver"


def _public_error(error: Exception) -> HTTPException:
    code = str(error).split(":", 1)[0]
    allowed = {
        "invalid_place_query",
        "unsupported_locale",
        "invalid_result_limit",
        "service_area_unsupported",
        "route_evidence_unavailable",
        "route_evidence_not_found",
        "route_evidence_expired",
        "route_changed",
        "quote_expired",
        "quote_changed",
        "authentication_required",
        "access_denied",
        "idempotency_conflict",
        "booking_validation_failed",
        "temporarily_unavailable",
        "pricing_unavailable",
    }
    public = code if code in allowed else "temporarily_unavailable"
    statuses = {
        "authentication_required": status.HTTP_401_UNAUTHORIZED,
        "access_denied": status.HTTP_403_FORBIDDEN,
        "route_evidence_not_found": status.HTTP_404_NOT_FOUND,
        "invalid_place_query": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "unsupported_locale": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_result_limit": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "temporarily_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "pricing_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    return HTTPException(
        statuses.get(public, status.HTTP_409_CONFLICT), {"code": public}
    )


def create_booking_router(
    application: BookingApplication, subject_resolver: TrustedSubjectResolver
) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/booking",
        tags=["mobile-booking"],
        route_class=AuthorizationRoute,
    )

    async def optional_subject(request: Request) -> AuthorizationSubject | None:
        if not request.headers.get("Authorization"):
            return None
        return await subject_resolver.resolve(request)

    @router.get("/places/search", response_model=tuple[PlaceCandidate, ...])
    async def search_places(
        query: Annotated[str, Query(min_length=2, max_length=120)],
        locale: Annotated[str, Query(pattern=r"^(en|am)$")] = "en",
        limit: Annotated[int, Query(ge=1, le=10)] = 8,
    ) -> tuple[PlaceCandidate, ...]:
        try:
            return application.search_places(
                query=query, locale=locale, limit=limit, at=datetime.now(UTC)
            )
        except (BookingConflict, TimeoutError) as error:
            raise _public_error(error) from error

    @router.post("/route-previews", response_model=RoutePreviewResponse)
    async def preview(
        command: RoutePreviewRequest, request: Request
    ) -> RoutePreviewResponse:
        try:
            item = application.preview(
                PreviewRouteCommand.model_validate(command.model_dump()),
                subject=await optional_subject(request),
                at=datetime.now(UTC),
            )
        except (BookingConflict, TimeoutError, ValueError) as error:
            raise _public_error(error) from error
        toll_message = (
            "Toll information unavailable."
            if item.route.toll_state
            in {TollEvidenceState.UNKNOWN, TollEvidenceState.UNSUPPORTED}
            else None
        )
        return RoutePreviewResponse(
            evidence_id=item.evidence_id,
            evidence_hash=item.evidence_hash,
            pickup=item.pickup.structured_address
            or item.pickup.landmark_reference
            or "Selected pickup",
            destination=item.destination.structured_address
            or item.destination.landmark_reference
            or "Selected destination",
            geometry=item.route.geometry,
            distance_metres=item.route.metrics.distance_meters,
            duration_seconds=item.route.metrics.duration_seconds,
            traffic_state=item.route.traffic_state.value,
            toll_state=item.route.toll_state.value,
            toll_amount_minor=item.route.toll_amount_minor,
            toll_message=toll_message,
            quote_id=item.quote.quote_id,
            currency=item.quote.breakdown.currency,
            estimated_fare_minor=item.quote.breakdown.rider_total_minor,
            pricing_version=item.quote.policy_version,
            fare_explanation=("Base fare", "Route distance", "Estimated travel time"),
            surge_applied=False,
            expires_at=item.quote.expires_at,
            attribution=item.route.attribution,
        )

    @router.post(
        "/confirm",
        response_model=ConfirmBookingResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_required("ride_request.create", resource_type="canonical_ride_request")
    async def confirm(
        command: ConfirmBookingRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> ConfirmBookingResponse:
        subject = await subject_resolver.resolve(request)
        if subject is None:
            raise HTTPException(401, {"code": "authentication_required"})
        try:
            item, ride = application.confirm(
                ConfirmBookingCommand(
                    **command.model_dump(), idempotency_key=idempotency_key
                ),
                subject=subject,
                at=datetime.now(UTC),
            )
        except (BookingConflict, ValueError) as error:
            raise _public_error(error) from error
        return ConfirmBookingResponse(
            confirmation_id=item.confirmation_id,
            ride_request_id=ride.request_id,
            state=ride.state.value,
            dispatch_started=getattr(application, "dispatch_enabled", False),
        )

    return router
