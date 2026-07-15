from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PassengerChannel(StrEnum):
    IDENTITY = "identity"
    VERIFIED_CONTACT = "verified_contact"
    ASSISTED = "assisted"


class NotificationKind(StrEnum):
    RESERVATION_ACCEPTED = "reservation_accepted"
    PASSENGER_CONFIRMATION_REQUESTED = "passenger_confirmation_requested"
    PASSENGER_CONFIRMED = "passenger_confirmed"
    PASSENGER_DECLINED = "passenger_declined"
    DRIVER_SOFT_PLANNED = "driver_soft_planned"
    DRIVER_COMMITTED = "driver_committed"
    MATERIAL_REASSIGNMENT = "material_reassignment"
    DRIVER_EN_ROUTE = "driver_en_route"
    READY_FOR_PICKUP = "ready_for_pickup"
    DELAY_OR_RECOVERY = "delay_or_recovery"
    RESERVATION_CANCELLED = "reservation_cancelled"
    NO_DRIVER_AVAILABLE = "no_driver_available"
    SUPPORT_HANDOFF = "support_handoff"


class CreateScheduledReservationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pickup_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    destination_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    service_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]
    quote_id: UUID
    requested_pickup_at: datetime
    requested_timezone: Annotated[str, Field(min_length=1, max_length=64)]
    passenger_channel: PassengerChannel = PassengerChannel.IDENTITY
    passenger_contact_reference: (
        Annotated[str, Field(min_length=16, max_length=128)] | None
    ) = None
    trusted_contact_reference: (
        Annotated[str, Field(min_length=16, max_length=128)] | None
    ) = None
    future_payer_reference: (
        Annotated[str, Field(min_length=16, max_length=128)] | None
    ) = None

    @field_validator("requested_pickup_at")
    @classmethod
    def aware_pickup(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Pickup time must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_passenger_reference(self) -> "CreateScheduledReservationCommand":
        if self.passenger_channel is PassengerChannel.IDENTITY:
            if self.passenger_contact_reference is not None:
                raise ValueError("Identity passenger cannot include contact reference")
        elif self.passenger_contact_reference is None:
            raise ValueError("Contact or assisted passenger requires contact reference")
        if self.pickup_place_id == self.destination_place_id:
            raise ValueError("Pickup and destination must differ")
        return self


class UpdateReservationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_pickup_at: datetime | None = None
    destination_place_id: Annotated[str, Field(min_length=8, max_length=128)] | None = (
        None
    )
    expected_version: Annotated[int, Field(ge=1)]

    @field_validator("requested_pickup_at")
    @classmethod
    def aware_pickup(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Pickup time must be timezone-aware")
        return value.astimezone(UTC)


class PickupVerificationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class DriverCommitmentResponseCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    expected_version: Annotated[int, Field(ge=1)]


class PublicReservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reservation_id: UUID
    state: str
    pickup_place_id: str
    destination_place_id: str
    service_type: str
    requested_pickup_at: datetime
    requested_timezone: str
    version: int
    requires_passenger_confirmation: bool


class NotificationMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    reservation_id: UUID
    recipient_reference: Annotated[str, Field(min_length=8, max_length=128)]
    kind: NotificationKind
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Notification time must be timezone-aware")
        return value.astimezone(UTC)
