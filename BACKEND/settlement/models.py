from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MinorAmount = Annotated[int, Field(ge=0, le=10_000_000_000)]


class ReconciliationType(StrEnum):
    RIDE_RECONCILIATION = "ride_reconciliation"
    PAYMENT_RECONCILIATION = "payment_reconciliation"
    REFUND_RECONCILIATION = "refund_reconciliation"
    PROVIDER_RECONCILIATION = "provider_reconciliation"
    SETTLEMENT_RECONCILIATION = "settlement_reconciliation"
    MANUAL_ADJUSTMENT_REVIEW = "manual_adjustment_review"


class ReconciliationResult(StrEnum):
    MATCHED = "matched"
    PARTIALLY_MATCHED = "partially_matched"
    MISMATCH = "mismatch"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class SettlementBatchState(StrEnum):
    CREATED = "created"
    COLLECTING = "collecting"
    RECONCILING = "reconciling"
    BALANCED = "balanced"
    READY_FOR_SETTLEMENT = "ready_for_settlement"
    EXCEPTION = "exception"
    MANUAL_REVIEW = "manual_review"
    RESOLVED = "resolved"


class ReconciliationExceptionType(StrEnum):
    DUPLICATE_PAYMENT = "duplicate_payment"
    MISSING_CALLBACK = "missing_callback"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    REFUND_MISMATCH = "refund_mismatch"
    ORPHAN_PAYMENT = "orphan_payment"
    LATE_CALLBACK = "late_callback"
    UNKNOWN_OUTCOME = "unknown_outcome"
    MANUAL_INVESTIGATION = "manual_investigation"
    MISSING_EXPECTED_RECORD = "missing_expected_record"
    MISSING_OBSERVED_RECORD = "missing_observed_record"
    REFERENCE_MISMATCH = "reference_mismatch"
    STATUS_MISMATCH = "status_mismatch"
    TIMING_MISMATCH = "timing_mismatch"
    UNAUTHORIZED_RECORD = "unauthorized_record"


class SettlementApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class SettlementEvidenceType(StrEnum):
    SUBMISSION = "submission"
    CONFIRMATION = "confirmation"
    FAILURE = "failure"


class ReconciliationTraceability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_request_id: UUID
    dispatch_handoff_id: UUID
    assignment_id: UUID
    active_ride_id: UUID
    fare_estimate_id: UUID
    fare_calculation_id: UUID
    ledger_journal_id: UUID


class SettlementBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    settlement_batch_id: UUID = Field(default_factory=uuid4)
    state: SettlementBatchState = SettlementBatchState.CREATED
    created_by_identity_id: UUID
    created_at: datetime
    last_transition_at: datetime
    ready_for_settlement_at: datetime | None = None
    metadata_safe: dict[str, str] = Field(default_factory=dict)
    correlation_id: UUID
    causation_id: UUID

    @field_validator("created_at", "last_transition_at", "ready_for_settlement_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def chronological(self) -> "SettlementBatch":
        if self.last_transition_at < self.created_at:
            raise ValueError("last_transition_at must not precede created_at")
        if (
            self.ready_for_settlement_at is not None
            and self.ready_for_settlement_at < self.created_at
        ):
            raise ValueError("ready_for_settlement_at must not precede created_at")
        return self


class SettlementItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    settlement_item_id: UUID = Field(default_factory=uuid4)
    settlement_batch_id: UUID
    ride_id: UUID
    fare_calculation_id: UUID
    payment_intent_id: UUID
    payment_attempt_id: UUID
    refund_request_id: UUID | None = None
    ledger_journal_id: UUID
    reconciliation_type: ReconciliationType
    amount_minor: MinorAmount
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    traceability: ReconciliationTraceability
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ReconciliationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reconciliation_record_id: UUID = Field(default_factory=uuid4)
    settlement_batch_id: UUID
    settlement_item_id: UUID
    reconciliation_type: ReconciliationType
    result: ReconciliationResult
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    decision_safe: dict[str, str] = Field(default_factory=dict)
    recorded_by_identity_id: UUID
    recorded_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("recorded_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ReconciliationException(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reconciliation_exception_id: UUID = Field(default_factory=uuid4)
    settlement_batch_id: UUID
    settlement_item_id: UUID
    exception_type: ReconciliationExceptionType
    exception_state: SettlementBatchState
    details_safe: dict[str, str] = Field(default_factory=dict)
    raised_by_identity_id: UUID
    raised_at: datetime
    resolution_code: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_.-]{2,62}$"
    )
    resolved_by_identity_id: UUID | None = None
    resolved_at: datetime | None = None
    correlation_id: UUID
    causation_id: UUID

    @field_validator("raised_at", "resolved_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def chronological(self) -> "ReconciliationException":
        if self.resolved_at is not None and self.resolved_at < self.raised_at:
            raise ValueError("resolved_at must not precede raised_at")
        return self


class SettlementApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    settlement_approval_id: UUID = Field(default_factory=uuid4)
    settlement_batch_id: UUID
    decision: SettlementApprovalDecision
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    prepared_by_identity_id: UUID
    decided_by_identity_id: UUID
    decided_by_actor_type: str = Field(pattern=r"^(staff|administrator)$")
    decided_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("decided_at")
    @classmethod
    def approval_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement approval timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def separation_of_duties(self) -> "SettlementApproval":
        if self.prepared_by_identity_id == self.decided_by_identity_id:
            raise ValueError("Settlement preparer cannot approve their own batch")
        return self


class SettlementHoldEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    settlement_hold_evidence_id: UUID = Field(default_factory=uuid4)
    settlement_batch_id: UUID
    financial_hold_id: UUID | None = None
    hold_state: str = Field(pattern=r"^[a-z_]{3,32}$")
    blocks_readiness: bool
    evaluated_by_identity_id: UUID
    evaluated_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("evaluated_at")
    @classmethod
    def hold_evidence_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement hold timestamps must be timezone-aware")
        return value.astimezone(UTC)


class SettlementExternalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    settlement_external_evidence_id: UUID = Field(default_factory=uuid4)
    settlement_batch_id: UUID
    evidence_type: SettlementEvidenceType
    provider_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    provider_reference: str = Field(min_length=8, max_length=128)
    evidence_fingerprint: str = Field(pattern=r"^[a-f0-9]{32,128}$")
    recorded_by_identity_id: UUID
    recorded_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("recorded_at")
    @classmethod
    def evidence_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Settlement evidence timestamps must be timezone-aware")
        return value.astimezone(UTC)
