from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DeliveryState(StrEnum):
    ARRIVING = "courier_arriving"
    AVAILABLE = "customer_available"
    VERIFIED = "delivery_verified"
    RECEIVED = "customer_received"
    COMPLETED = "courier_delivery_completed"
    CLOSED = "chain_of_custody_closed"


class DeliveryAction(StrEnum):
    MARK_ARRIVING = "mark_arriving"
    CUSTOMER_AVAILABLE = "customer_available"
    VERIFY = "verify_delivery"
    CONFIRM_RECEIVED = "confirm_received"
    COMPLETE = "complete_delivery"
    CLOSE = "close_custody"
    CUSTOMER_UNAVAILABLE = "customer_unavailable"


class DeliveryVerificationMethod(StrEnum):
    QR = "qr_code"
    MANUAL = "manual_code"


class DeliveryCredential(BaseModel):
    model_config = ConfigDict(frozen=True)
    credential_id: UUID
    order_id: UUID
    order_number: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime


class DeliveryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivery_id: UUID
    custody_id: UUID
    order_id: UUID
    merchant_id: UUID
    courier_identity_id: UUID
    credential_id: UUID
    state: DeliveryState
    version: int
    arriving_at: datetime | None
    customer_available_at: datetime | None
    verified_at: datetime | None
    verification_method: DeliveryVerificationMethod | None
    customer_received_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    updated_at: datetime


class DeliveryEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID
    delivery_id: UUID
    event_type: str
    from_state: DeliveryState | None
    to_state: DeliveryState
    actor_identity_id: UUID | None
    version: int
    occurred_at: datetime


class DeliveryView(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivery: DeliveryRecord
    credential: DeliveryCredential
    events: tuple[DeliveryEvent, ...]


class DeliveryCredentialView(BaseModel):
    model_config = ConfigDict(frozen=True)
    credential: DeliveryCredential
    display_code: str
