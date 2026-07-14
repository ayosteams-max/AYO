from typing import Annotated

from fastapi import APIRouter, Depends

from BACKEND.repositories.contracts import RideRepository
from BACKEND.repositories.registry import get_ride_repository
from BACKEND.schemas.ride import RideRequest, RideResponse
from BACKEND.services.ride_service import create_ride

router = APIRouter(prefix="/rides", tags=["Rides"])


@router.post("/", response_model=RideResponse)
def request_ride(
    request: RideRequest,
    repository: Annotated[RideRepository, Depends(get_ride_repository)],
):
    return create_ride(request, repository)
