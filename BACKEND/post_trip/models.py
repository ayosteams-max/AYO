from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Minor = Annotated[int, Field(ge=0, le=10_000_000_000)]


class PaymentMethod(StrEnum):
    CASH = "cash"
    LICENSED_DIGITAL_PROVIDER = "licensed_digital_provider"


class CashSettlementState(StrEnum):
    AWAITING_CONFIRMATIONS = "awaiting_confirmations"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CASH_SETTLED = "cash_settled"
    CASH_SETTLEMENT_REVIEW = "cash_settlement_review"


class PostTripState(StrEnum):
    EVIDENCE_FINALIZED = "evidence_finalized"
    AWAITING_SETTLEMENT = "awaiting_settlement"
    SETTLED = "settled"
    ARCHIVED = "archived"


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authority: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")
    reference_id: str = Field(min_length=8, max_length=128)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: dict[str, int | str] = Field(default_factory=dict)


class TripEvidencePackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    package_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    rider_identity_id: UUID
    driver_identity_id: UUID
    vehicle_id: UUID
    payment_method: PaymentMethod
    booking: EvidenceReference
    route: EvidenceReference
    pricing: EvidenceReference
    dispatch: EvidenceReference
    assignment: EvidenceReference
    timeline: EvidenceReference
    completion: EvidenceReference
    payment: EvidenceReference | None = None
    schema_version: str = Field(pattern=r"^post_trip\.evidence\.v[0-9]+$")
    package_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalized_at: datetime

    @model_validator(mode="after")
    def payment_evidence(self) -> "TripEvidencePackage":
        if (
            self.payment_method is PaymentMethod.LICENSED_DIGITAL_PROVIDER
            and self.payment is None
        ):
            raise ValueError(
                "Digital settlement requires licensed-provider payment evidence"
            )
        if self.payment_method is PaymentMethod.CASH and self.payment is not None:
            raise ValueError("Cash settlement cannot carry digital payment evidence")
        return self

    @field_validator("finalized_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Post-trip timestamps must be timezone-aware")
        return value.astimezone(UTC)


class FinancialBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    currency: str = Field(pattern=r"^ETB$")
    gross_fare_minor: Minor
    commission_minor: Minor
    incentives_minor: Minor = 0
    taxes_minor: Minor
    adjustments_minor: int = Field(ge=-10_000_000_000, le=10_000_000_000)
    net_driver_earnings_minor: Minor
    policy_version: str = Field(min_length=2, max_length=63)
    policy_evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fare_estimate_id: UUID
    fare_calculation_id: UUID

    @model_validator(mode="after")
    def equation(self) -> "FinancialBreakdown":
        expected = (
            self.gross_fare_minor
            - self.commission_minor
            - self.taxes_minor
            + self.incentives_minor
            + self.adjustments_minor
        )
        if expected < 0 or self.net_driver_earnings_minor != expected:
            raise ValueError("Net driver earnings do not match approved components")
        return self


class CashConfirmation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    confirmation_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    actor_identity_id: UUID
    actor_role: str = Field(pattern=r"^(rider|driver)$")
    confirmed: bool
    idempotency_key_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_at: datetime


class Rating(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rating_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    author_identity_id: UUID
    target_identity_id: UUID
    stars: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=1000)
    preference_requested: bool = False
    submitted_at: datetime
    window_expires_at: datetime


class PreferenceSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    preference_id: UUID = Field(default_factory=uuid4)
    owner_identity_id: UUID
    capability: str = Field(pattern=r"^(ride|eat|marketplace|home_services|business)$")
    target_type: str = Field(pattern=r"^(driver|restaurant|seller|provider|merchant)$")
    target_identity_id: UUID
    source_ride_id: UUID | None = None
    active: bool = True
    created_at: datetime
    revoked_at: datetime | None = None


class Receipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    receipt_id: UUID = Field(default_factory=uuid4)
    receipt_number: str = Field(pattern=r"^AYO-RIDE-[A-Z0-9-]{8,40}$")
    ride_id: UUID
    issued_to_identity_id: UUID
    receipt_type: str = Field(pattern=r"^(rider_receipt|driver_settlement_summary)$")
    payload: dict[str, object]
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    legal_entity: str = Field(min_length=2, max_length=160)
    regulatory_policy_version: str = Field(min_length=2, max_length=63)
    issued_at: datetime


class PostTripRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_id: UUID
    package_id: UUID
    state: PostTripState
    cash_state: CashSettlementState | None
    financial_breakdown: FinancialBreakdown
    ledger_journal_id: UUID | None = None
    wallet_entry_id: UUID | None = None
    rider_receipt_id: UUID | None = None
    driver_receipt_id: UUID | None = None
    archived_at: datetime | None = None
    version: int = Field(ge=1)
