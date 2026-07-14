from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.repositories.contracts import RideRepository
from BACKEND.repositories.registry import get_ride_repository

router = APIRouter(
    prefix="/driver-offers",
    tags=["Driver Offers"],
)


class DriverOfferDecision(BaseModel):
    ride_id: str = Field(min_length=1, max_length=50)
    driver_id: str = Field(min_length=1, max_length=50)


def verify_offer(
    ride_id: str,
    driver_id: str,
    repository: RideRepository,
) -> Ride:
    ride = repository.get(ride_id)

    if ride is None:
        raise HTTPException(
            status_code=404,
            detail="Ride not found.",
        )

    if ride.driver_id != driver_id:
        raise HTTPException(
            status_code=403,
            detail="This ride offer belongs to another driver.",
        )

    if ride.status != RideStatus.WAITING_FOR_DRIVER:
        raise HTTPException(
            status_code=409,
            detail=f"Ride cannot be changed from status: {ride.status.value}",
        )

    return ride


@router.post("/accept")
def accept_offer(
    decision: DriverOfferDecision,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    verify_offer(
        ride_id=decision.ride_id,
        driver_id=decision.driver_id,
        repository=repository,
    )

    updated_ride = repository.update_status(
        decision.ride_id, RideStatus.DRIVER_ACCEPTED
    )

    return {
        "message": "Driver accepted the ride offer.",
        "ride": updated_ride.to_legacy_dict() if updated_ride else None,
    }


@router.post("/decline")
def decline_offer(
    decision: DriverOfferDecision,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    verify_offer(
        ride_id=decision.ride_id,
        driver_id=decision.driver_id,
        repository=repository,
    )

    updated_ride = repository.update_status(
        decision.ride_id, RideStatus.DRIVER_DECLINED
    )

    return {
        "message": "Driver declined. AYO will search for another driver.",
        "ride": updated_ride.to_legacy_dict() if updated_ride else None,
    }
