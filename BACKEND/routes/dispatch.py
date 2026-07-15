from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.dispatch.application import DispatchApplication
from BACKEND.dispatch.contracts import DispatchConflict, IdempotencyConflict
from BACKEND.dispatch.models import CreateRideCommand, DriverOffer, RideProjection
from BACKEND.dispatch.service import QuoteExpired
from BACKEND.identity.models import IdentityType


class PublicRideResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_id: UUID
    state: str
    version: int
    pickup_name: str
    destination_name: str
    service_type: str
    estimated_fare_minor: int
    currency: str

    @classmethod
    def from_projection(cls, ride: RideProjection) -> "PublicRideResponse":
        return cls(
            ride_id=ride.ride_id,
            state=ride.state.value,
            version=ride.version,
            pickup_name=ride.pickup.display_name,
            destination_name=ride.destination.display_name,
            service_type=ride.service_type,
            estimated_fare_minor=ride.estimated_fare_minor,
            currency=ride.currency,
        )


class DriverOfferResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    offer_id: UUID
    ride_id: UUID
    expires_at: str

    @classmethod
    def from_offer(cls, offer: DriverOffer) -> "DriverOfferResponse":
        return cls(
            offer_id=offer.offer_id,
            ride_id=offer.ride_id,
            expires_at=offer.expires_at.isoformat(),
        )


def _subject(request: Request, expected: IdentityType) -> AuthorizationSubject:
    subject: AuthorizationSubject | None = getattr(
        request.state, "authorization_subject", None
    )
    if subject is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    if subject.identity_type is not expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied.")
    return subject


def create_dispatch_router(application: DispatchApplication) -> APIRouter:
    router = APIRouter(
        prefix="/dispatch", tags=["dispatch"], route_class=AuthorizationRoute
    )

    @router.post(
        "/rides", response_model=PublicRideResponse, status_code=status.HTTP_201_CREATED
    )
    @permission_required("dispatch.rider.request", resource_type="ride")
    def create_ride(
        command: CreateRideCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> PublicRideResponse:
        subject = _subject(request, IdentityType.RIDER)
        try:
            ride, _ = application.create_ride(
                rider_id=subject.identity_id,
                idempotency_key=idempotency_key,
                command=command,
            )
            if ride.state.value == "searching":
                application.dispatch_next(ride.ride_id)
            recovered = application.recover_ride(subject.identity_id)
            return PublicRideResponse.from_projection(recovered or ride)
        except QuoteExpired as error:
            raise HTTPException(status.HTTP_409_CONFLICT, "Quote expired.") from error
        except IdempotencyConflict as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Idempotency conflict."
            ) from error
        except DispatchConflict as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Ride state conflict."
            ) from error

    @router.get("/rides/active", response_model=PublicRideResponse | None)
    @permission_required("dispatch.rider.request", resource_type="ride")
    def active_ride(request: Request) -> PublicRideResponse | None:
        subject = _subject(request, IdentityType.RIDER)
        ride = application.recover_ride(subject.identity_id)
        return None if ride is None else PublicRideResponse.from_projection(ride)

    @router.get("/offers/{offer_id}", response_model=DriverOfferResponse)
    @permission_required(
        "dispatch.driver.offer.respond",
        resource_type="driver_offer",
        resource_id_parameter="offer_id",
    )
    def get_offer(offer_id: UUID, request: Request) -> DriverOfferResponse:
        subject = _subject(request, IdentityType.DRIVER)
        offer = application.get_offer(offer_id)
        if offer is None or offer.driver_id != subject.identity_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found.")
        return DriverOfferResponse.from_offer(offer)

    @router.post("/offers/{offer_id}/accept", response_model=PublicRideResponse)
    @permission_required(
        "dispatch.driver.offer.respond",
        resource_type="driver_offer",
        resource_id_parameter="offer_id",
    )
    def accept_offer(offer_id: UUID, request: Request) -> PublicRideResponse:
        subject = _subject(request, IdentityType.DRIVER)
        try:
            return PublicRideResponse.from_projection(
                application.accept_offer(offer_id, subject.identity_id)
            )
        except DispatchConflict as error:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Offer not found."
            ) from error

    @router.post("/offers/{offer_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
    @permission_required(
        "dispatch.driver.offer.respond",
        resource_type="driver_offer",
        resource_id_parameter="offer_id",
    )
    def decline_offer(offer_id: UUID, request: Request) -> None:
        subject = _subject(request, IdentityType.DRIVER)
        try:
            application.decline_offer(offer_id, subject.identity_id)
        except DispatchConflict as error:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Offer not found."
            ) from error

    return router
