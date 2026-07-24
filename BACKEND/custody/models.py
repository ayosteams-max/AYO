from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustodyState(StrEnum):
    WAITING = "waiting_for_pickup"
    SEALED = "order_sealed"
    VERIFIED = "pickup_verified"
    RELEASED = "merchant_released"
    ACCEPTED = "courier_custody_accepted"


class VerificationMethod(StrEnum):
    QR = "qr_code"
    BARCODE = "barcode"


class CustodyAction(StrEnum):
    SEAL = "seal_order"
    VERIFY = "verify_pickup"
    RELEASE = "release_order"
    ACCEPT = "accept_custody"


class CustodyRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    custody_id: UUID
    pickup_id: UUID
    order_id: UUID
    merchant_id: UUID
    courier_identity_id: UUID
    state: CustodyState
    version: int
    sealed_at: datetime | None
    verified_at: datetime | None
    verification_method: VerificationMethod | None
    merchant_released_at: datetime | None
    custody_accepted_at: datetime | None
    updated_at: datetime


class PickupChallenge(BaseModel):
    model_config = ConfigDict(frozen=True)
    challenge_id: UUID
    custody_id: UUID
    expires_at: datetime
    used_at: datetime | None


class CustodyEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID
    custody_id: UUID
    event_type: str
    from_state: CustodyState | None
    to_state: CustodyState
    actor_identity_id: UUID
    version: int
    occurred_at: datetime


class CustodyView(BaseModel):
    model_config = ConfigDict(frozen=True)
    custody: CustodyRecord
    challenge: PickupChallenge | None
    events: tuple[CustodyEvent, ...]


class IssuedPickupCode(BaseModel):
    model_config = ConfigDict(frozen=True)
    view: CustodyView
    display_code: str
