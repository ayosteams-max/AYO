from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.repositories.contracts import LegacyWalletRepository, RideRepository
from BACKEND.repositories.registry import get_ride_repository, get_wallet_repository
from BACKEND.services.wallet_service import add_trip_earning

router = APIRouter(
    prefix="/ride-status",
    tags=["Ride Status"],
)


class RideStatusUpdate(BaseModel):
    ride_id: str = Field(min_length=1, max_length=50)
    driver_id: str = Field(min_length=1, max_length=50)


class CompleteTripRequest(BaseModel):
    ride_id: str = Field(min_length=1, max_length=50)
    driver_id: str = Field(min_length=1, max_length=50)

    gross_fare: float = Field(gt=0)

    payment_method: Literal[
        "CASH",
        "AYO_WALLET",
        "CARD",
        "MOBILE_MONEY",
    ]

    tip: float = Field(default=0, ge=0)
    bonus: float = Field(default=0, ge=0)


def verify_driver(
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
            detail="This ride belongs to another driver.",
        )

    return ride


def change_status(
    decision: RideStatusUpdate,
    required_status: RideStatus,
    new_status: RideStatus,
    message: str,
    repository: RideRepository,
) -> dict:
    ride = verify_driver(
        ride_id=decision.ride_id,
        driver_id=decision.driver_id,
        repository=repository,
    )

    if ride.status != required_status:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ride must be {required_status.value} "
                f"before changing to {new_status.value}. "
                f"Current status: {ride.status.value}"
            ),
        )

    updated_ride = repository.update_status(decision.ride_id, new_status)

    return {
        "message": message,
        "ride": updated_ride.to_legacy_dict() if updated_ride else None,
    }


@router.get("/{ride_id}")
def check_ride_status(
    ride_id: str,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    ride = repository.get(ride_id)

    if ride is None:
        raise HTTPException(
            status_code=404,
            detail="Ride not found.",
        )

    return ride.to_legacy_dict()


@router.post("/on-the-way")
def driver_on_the_way(
    decision: RideStatusUpdate,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    return change_status(
        decision=decision,
        required_status=RideStatus.DRIVER_ACCEPTED,
        new_status=RideStatus.DRIVER_ON_THE_WAY,
        message="Driver is on the way to the rider.",
        repository=repository,
    )


@router.post("/arrived")
def driver_arrived(
    decision: RideStatusUpdate,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    return change_status(
        decision=decision,
        required_status=RideStatus.DRIVER_ON_THE_WAY,
        new_status=RideStatus.DRIVER_ARRIVED,
        message="Driver has arrived at the pickup location.",
        repository=repository,
    )


@router.post("/start")
def start_trip(
    decision: RideStatusUpdate,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    return change_status(
        decision=decision,
        required_status=RideStatus.DRIVER_ARRIVED,
        new_status=RideStatus.TRIP_STARTED,
        message="Trip has started.",
        repository=repository,
    )


@router.post("/complete")
def complete_trip(
    request: CompleteTripRequest,
    ride_repository: Annotated[RideRepository, Depends(get_ride_repository)],
    wallet_repository: Annotated[
        LegacyWalletRepository, Depends(get_wallet_repository)
    ],
):
    ride = verify_driver(
        ride_id=request.ride_id,
        driver_id=request.driver_id,
        repository=ride_repository,
    )

    if ride.status != RideStatus.TRIP_STARTED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Ride must be TRIP_STARTED before completion. "
                f"Current status: {ride.status.value}"
            ),
        )

    try:
        wallet_result = add_trip_earning(
            driver_id=request.driver_id,
            ride_id=request.ride_id,
            gross_fare=request.gross_fare,
            payment_method=request.payment_method,
            tip=request.tip,
            bonus=request.bonus,
            repository=wallet_repository,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    ride.status = RideStatus.TRIP_COMPLETED
    ride.gross_fare = request.gross_fare
    ride.payment_method = request.payment_method
    ride.tip = request.tip
    ride.bonus = request.bonus
    updated_ride = ride_repository.save(ride)

    return {
        "message": "Trip completed and driver earnings added.",
        "ride": updated_ride.to_legacy_dict(),
        "earnings": wallet_result["breakdown"],
        "wallet": wallet_result["wallet"],
    }
