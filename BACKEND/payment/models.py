from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MinorAmount = Annotated[int, Field(ge=0, le=10_000_000_000)]


class PaymentMethodFamily(StrEnum):
    CASH = "cash"
    MOBILE_MONEY = "mobile_money"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    UNKNOWN = "unknown"


class PaymentIntentState(StrEnum):
    CREATED = "created"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentAttemptState(StrEnum):
    CREATED = "created"
    AUTHORIZATION_PENDING = "authorization_pending"
    AUTHORIZED = "authorized"
    CAPTURE_PENDING = "capture_pending"
    CAPTURED = "captured"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    OUTCOME_UNKNOWN = "outcome_unknown"


class PaymentActor(StrEnum):
    RIDER = "rider"
    DRIVER = "driver"
    STAFF = "staff"
    SERVICE = "service"
    PROVIDER = "provider"
    SYSTEM = "system"


class PaymentTraceability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_request_id: UUID
    dispatch_handoff_id: UUID
    assignment_id: UUID
    active_ride_id: UUID
    fare_estimate_id: UUID
    fare_calculation_id: UUID
    ledger_journal_id: UUID | None = None


class PaymentIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payment_intent_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    rider_identity_id: UUID
    passenger_identity_id: UUID
    booker_identity_id: UUID
    payer_identity_id: UUID
    amount_minor: MinorAmount
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    payment_method_family: PaymentMethodFamily
    state: PaymentIntentState = PaymentIntentState.CREATED
    traceability: PaymentTraceability
    metadata_safe: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    expires_at: datetime | None = None
    cancelled_at: datetime | None = None

    @field_validator("created_at", "expires_at", "cancelled_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Payment timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_identities(self) -> "PaymentIntent":
        if self.payer_identity_id != self.rider_identity_id:
            raise ValueError("payer_identity_id must match rider_identity_id")
        if self.amount_minor < 0:
            raise ValueError("amount_minor must be non-negative")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if self.cancelled_at is not None and self.cancelled_at < self.created_at:
            raise ValueError("cancelled_at must not precede created_at")
        return self


class PaymentAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payment_attempt_id: UUID = Field(default_factory=uuid4)
    payment_intent_id: UUID
    provider_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    provider_reference: str = Field(min_length=3, max_length=128)
    provider_event_id: str | None = Field(default=None, min_length=3, max_length=128)
    state: PaymentAttemptState = PaymentAttemptState.CREATED
    amount_minor: MinorAmount
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    reason_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    correlation_id: UUID
    causation_id: UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Payment timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def chronological(self) -> "PaymentAttempt":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class PaymentCallbackEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    callback_id: UUID = Field(default_factory=uuid4)
    provider_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    provider_event_id: str = Field(min_length=3, max_length=128)
    provider_signature_fingerprint: str = Field(pattern=r"^[a-z0-9]{16,128}$")
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    received_at: datetime
    replay_window_ends_at: datetime
    correlated_attempt_id: UUID | None = None
    processed_at: datetime | None = None

    @field_validator("received_at", "replay_window_ends_at", "processed_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Payment timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def chronological(self) -> "PaymentCallbackEnvelope":
        if self.replay_window_ends_at <= self.received_at:
            raise ValueError("replay_window_ends_at must be later than received_at")
        if self.processed_at is not None and self.processed_at < self.received_at:
            raise ValueError("processed_at must not precede received_at")
        return self
