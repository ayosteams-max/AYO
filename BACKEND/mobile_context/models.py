from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MerchantContextAvailability(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    SUSPENDED = "suspended"


class CourierContextAvailability(StrEnum):
    CURRENT_PICKUP = "current_pickup"


class PersonalMobileContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    available: Literal[True] = True


class MerchantMobileContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    merchant_id: UUID
    display_name: str = Field(min_length=2, max_length=120)
    availability: MerchantContextAvailability


class CourierMobileContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pickup_id: UUID
    availability: CourierContextAvailability = CourierContextAvailability.CURRENT_PICKUP


class MobileContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    personal: PersonalMobileContext | None
    merchants: tuple[MerchantMobileContext, ...] = Field(max_length=50)
    courier: CourierMobileContext | None
