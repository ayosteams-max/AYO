from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FinancialHoldType(StrEnum):
    RIDER_PAYMENT = "rider_payment"
    DRIVER_PAYOUT = "driver_payout"
    WALLET = "wallet"
    REFUND = "refund"
    SETTLEMENT = "settlement"
    FRAUD_REVIEW = "fraud_review"
    COMPLIANCE_REVIEW = "compliance_review"
    FINANCE_MANUAL_REVIEW = "finance_manual_review"


class FinancialHoldState(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    RELEASED = "released"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class FinancialHoldSourceType(StrEnum):
    PAYMENT_ATTEMPT = "payment_attempt"
    SETTLEMENT_BATCH = "settlement_batch"
    WALLET_ACCOUNT = "wallet_account"
    REFUND_REQUEST = "refund_request"
    FINANCIAL_POSTING = "financial_posting"
    IDENTITY = "identity"


class FinancialHoldReasonCode(StrEnum):
    PAYMENT_RISK_SIGNAL = "payment.risk_signal"
    PAYMENT_CHARGE_DISPUTE_RISK = "payment.charge_dispute_risk"
    PAYOUT_RECONCILIATION_GAP = "payout.reconciliation_gap"
    PAYOUT_IDENTITY_VERIFICATION = "payout.identity_verification"
    WALLET_LINEAGE_REVIEW = "wallet.lineage_review"
    WALLET_MANUAL_REVIEW = "wallet.manual_review"
    REFUND_POLICY_REVIEW = "refund.policy_review"
    REFUND_FRAUD_SIGNAL = "refund.fraud_signal"
    SETTLEMENT_EXCEPTION_REVIEW = "settlement.exception_review"
    SETTLEMENT_MANUAL_REVIEW = "settlement.manual_review"
    FRAUD_REVIEW_REQUIRED = "fraud.review_required"
    COMPLIANCE_REVIEW_REQUIRED = "compliance.review_required"
    FINANCE_MANUAL_REVIEW_REQUIRED = "finance.manual_review_required"


class HoldReason(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason_code: FinancialHoldReasonCode
    reason_detail: Annotated[str | None, Field(default=None, max_length=240)]


class FinancialHoldCreateCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hold_type: FinancialHoldType
    source_type: FinancialHoldSourceType
    source_id: UUID
    reason: HoldReason
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID
    causation_id: UUID
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Financial hold timestamps must be timezone-aware")
        return value.astimezone(UTC)


class FinancialHoldTransitionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_state: FinancialHoldState
    reason: HoldReason
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID
    causation_id: UUID
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Financial hold timestamps must be timezone-aware")
        return value.astimezone(UTC)


class FinancialHold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hold_id: UUID = Field(default_factory=uuid4)
    hold_type: FinancialHoldType
    source_type: FinancialHoldSourceType
    source_id: UUID
    reason_code: FinancialHoldReasonCode
    reason_detail: str | None = None
    state: FinancialHoldState
    created_by_identity_id: UUID
    correlation_id: UUID
    causation_id: UUID
    created_at: datetime
    updated_at: datetime
    metadata_safe: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Financial hold timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def chronological(self) -> "FinancialHold":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class FinancialHoldStateHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    history_id: UUID = Field(default_factory=uuid4)
    hold_id: UUID
    from_state: FinancialHoldState | None
    to_state: FinancialHoldState
    reason_code: FinancialHoldReasonCode
    reason_detail: str | None = None
    changed_by_identity_id: UUID
    changed_at: datetime
    correlation_id: UUID
    causation_id: UUID
    metadata_safe: dict[str, str] = Field(default_factory=dict)

    @field_validator("changed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Financial hold timestamps must be timezone-aware")
        return value.astimezone(UTC)


class FinancialHoldResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hold: FinancialHold
    history: tuple[FinancialHoldStateHistory, ...]
