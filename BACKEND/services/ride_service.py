import math
import uuid

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.models.driver import Driver, DriverStatus, VehicleType
from BACKEND.repositories.contracts import RideRepository
from BACKEND.repositories.registry import get_ride_repository
from BACKEND.schemas.ride import RideRequest, RideResponse, RideType
from BACKEND.services.dispatch_service import (
    build_driver_queue,
    send_ride_offer,
)
from BACKEND.services.driver_service import DRIVERS


def calculate_distance_km(
    rider_latitude: float,
    rider_longitude: float,
    driver_latitude: float,
    driver_longitude: float,
) -> float:
    """Calculate straight-line distance using the Haversine formula."""

    earth_radius_km = 6371.0

    rider_latitude_radians = math.radians(rider_latitude)
    driver_latitude_radians = math.radians(driver_latitude)

    latitude_difference = math.radians(driver_latitude - rider_latitude)
    longitude_difference = math.radians(driver_longitude - rider_longitude)

    value = (
        math.sin(latitude_difference / 2) ** 2
        + math.cos(rider_latitude_radians)
        * math.cos(driver_latitude_radians)
        * math.sin(longitude_difference / 2) ** 2
    )

    angle = 2 * math.atan2(
        math.sqrt(value),
        math.sqrt(1 - value),
    )

    return earth_radius_km * angle


def driver_is_eligible(
    driver: Driver,
    ride_type: RideType,
) -> bool:
    """Check whether a driver is suitable for this ride."""

    if driver.status != DriverStatus.AVAILABLE:
        return False

    if not driver.verified:
        return False

    if ride_type == RideType.AIRPORT_PREMIUM:
        return driver.airport_eligible and driver.premium_eligible

    if ride_type == RideType.AIRPORT:
        return driver.airport_eligible

    if ride_type == RideType.PREMIUM:
        return driver.premium_eligible

    if ride_type == RideType.XL:
        return driver.vehicle_type == VehicleType.XL

    if ride_type == RideType.STANDARD:
        return driver.vehicle_type in {
            VehicleType.STANDARD,
            VehicleType.PREMIUM,
            VehicleType.XL,
        }

    return False


def find_ranked_drivers(
    request: RideRequest,
) -> list[tuple[Driver, float]]:
    """
    Create an ordered list of suitable drivers.

    Immediate rides:
    - Closest safe suitable driver first.
    - Rating breaks a distance tie.

    Later, scheduled rides will use a separate planning score.
    """

    candidates: list[tuple[Driver, float]] = []

    for driver in DRIVERS:
        if not driver_is_eligible(driver, request.ride_type):
            continue

        distance_km = calculate_distance_km(
            rider_latitude=request.pickup_latitude,
            rider_longitude=request.pickup_longitude,
            driver_latitude=driver.latitude,
            driver_longitude=driver.longitude,
        )

        candidates.append((driver, distance_km))

    candidates.sort(
        key=lambda item: (
            item[1],
            -item[0].rating,
        )
    )

    return candidates


def create_ride(
    request: RideRequest,
    repository: RideRepository | None = None,
) -> RideResponse:
    """
    Create a ride and privately prepare backup drivers.

    Only the first driver receives the live offer.
    Other drivers remain invisible in the queue.
    """

    ride_repository = repository or get_ride_repository()
    ride_id = str(uuid.uuid4())[:8]

    ranked_candidates = find_ranked_drivers(request)

    if not ranked_candidates:
        ride = Ride(
            ride_id=ride_id,
            rider_name=request.rider_name,
            pickup=request.pickup,
            destination=request.destination,
            ride_type=request.ride_type.value,
            status=RideStatus.SEARCHING_FOR_DRIVER,
        )

        ride_repository.save(ride)

        return RideResponse(
            ride_id=ride.ride_id,
            rider_name=ride.rider_name,
            pickup=ride.pickup,
            destination=ride.destination,
            ride_type=RideType(ride.ride_type),
            driver_id=None,
            driver_name=None,
            driver_distance_km=None,
            status=ride.status.value,
        )

    driver_queue = build_driver_queue(ranked_candidates)

    first_driver, first_distance_km = ranked_candidates[0]

    current_offer = send_ride_offer(
        ride_id=ride_id,
        driver=first_driver,
    )

    driver_queue[0]["offer_status"] = "OFFER_SENT"

    ride = Ride(
        ride_id=ride_id,
        rider_name=request.rider_name,
        pickup=request.pickup,
        destination=request.destination,
        ride_type=request.ride_type.value,
        # Only this driver currently has the live offer.
        driver_id=first_driver.driver_id,
        driver_name=first_driver.full_name,
        driver_distance_km=round(first_distance_km, 2),
        status=RideStatus.WAITING_FOR_DRIVER,
        # Private dispatch information.
        driver_queue=driver_queue,
        current_offer_index=0,
        current_offer=current_offer,
    )

    ride_repository.save(ride)

    return RideResponse(
        ride_id=ride.ride_id,
        rider_name=ride.rider_name,
        pickup=ride.pickup,
        destination=ride.destination,
        ride_type=RideType(ride.ride_type),
        driver_id=ride.driver_id,
        driver_name=ride.driver_name,
        driver_distance_km=ride.driver_distance_km,
        status=ride.status.value,
    )
