from enum import Enum

from pydantic import BaseModel, Field


class DriverStatus(str, Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"


class VehicleType(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    XL = "xl"


class Driver(BaseModel):
    driver_id: str
    full_name: str = Field(min_length=2, max_length=100)
    phone_number: str = Field(min_length=8, max_length=20)

    latitude: float
    longitude: float

    vehicle_type: VehicleType
    vehicle_model: str
    vehicle_plate: str

    status: DriverStatus = DriverStatus.OFFLINE
    rating: float = Field(default=5.0, ge=0, le=5)
    completed_trips: int = Field(default=0, ge=0)

    premium_eligible: bool = False
    airport_eligible: bool = False
    verified: bool = False
