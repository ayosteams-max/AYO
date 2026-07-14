from enum import Enum

from pydantic import BaseModel, Field


class RideType(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    XL = "xl"
    AIRPORT = "airport"
    AIRPORT_PREMIUM = "airport_premium"


class RideRequest(BaseModel):
    rider_name: str = Field(min_length=2, max_length=100)
    pickup: str = Field(min_length=3, max_length=200)
    destination: str = Field(min_length=3, max_length=200)

    pickup_latitude: float = Field(ge=-90, le=90)
    pickup_longitude: float = Field(ge=-180, le=180)

    ride_type: RideType = RideType.STANDARD


class RideResponse(BaseModel):
    ride_id: str
    rider_name: str
    pickup: str
    destination: str
    ride_type: RideType
    driver_id: str | None = None
    driver_name: str | None = None
    driver_distance_km: float | None = None
    status: str
