from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MinorAmount = Annotated[int, Field(ge=0, le=10_000_000_000)]


class RefundType(StrEnum):
    PARTIAL_REFUND = "partial_refund"
    FULL_REFUND = "full_refund"
    ADMINISTRATIVE_ADJUSTMENT = "administrative_adjustment"
    CUSTOMER_GOODWILL_ADJUSTMENT = "customer_goodwill_adjustment"
    SYSTEM_CORRECTION_REQUEST = "system_correction_request"


class RefundRequestState(StrEnum):
    REQUESTED = "requested"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    REJECTED = "rejected"


class RefundDecisionType(StrEnum):
    REVIEW = "review"
    INVESTIGATION = "investigation"
    APPROVAL = "approval"
    REJECTION = "rejection"
    SCHEDULING = "scheduling"
    COMPLETION = "completion"


class RefundAuthorizationType(StrEnum):
    FINANCE_APPROVAL = "finance_approval"


class RefundTraceability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_request_id: UUID
    dispatch_handoff_id: UUID
    assignment_id: UUID
    active_ride_id: UUID
    fare_estimate_id: UUID
    fare_calculation_id: UUID
    ledger_journal_id: UUID


class RefundRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    refund_request_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    fare_calculation_id: UUID
    payment_intent_id: UUID
    payment_attempt_id: UUID
    ledger_journal_id: UUID
    refund_type: RefundType
    state: RefundRequestState = RefundRequestState.REQUESTED
    amount_minor: MinorAmount
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    requested_by_identity_id: UUID
    requested_at: datetime
    last_transition_at: datetime
    completed_at: datetime | None = None
    rejected_at: datetime | None = None
    correlation_id: UUID
    causation_id: UUID
    metadata_safe: dict[str, str] = Field(default_factory=dict)
    traceability: RefundTraceability

    @field_validator(
        "requested_at", "last_transition_at", "completed_at", "rejected_at"
    )
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Refund timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def chronological(self) -> "RefundRequest":
        if self.last_transition_at < self.requested_at:
            raise ValueError("last_transition_at must not precede requested_at")
        if self.completed_at is not None and self.completed_at < self.requested_at:
            raise ValueError("completed_at must not precede requested_at")
        if self.rejected_at is not None and self.rejected_at < self.requested_at:
            raise ValueError("rejected_at must not precede requested_at")
        return self


class RefundDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    refund_request_id: UUID
    decision_type: RefundDecisionType
    decision_outcome: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    decided_by_identity_id: UUID
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    decision_safe: dict[str, str] = Field(default_factory=dict)
    decided_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("decided_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Refund timestamps must be timezone-aware")
        return value.astimezone(UTC)


class RefundAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: UUID = Field(default_factory=uuid4)
    refund_request_id: UUID
    authorization_type: RefundAuthorizationType
    authorized_by_identity_id: UUID
    authority_permission: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    authorization_safe: dict[str, str] = Field(default_factory=dict)
    authorized_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("authorized_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Refund timestamps must be timezone-aware")
        return value.astimezone(UTC)


class RefundEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: UUID = Field(default_factory=uuid4)
    refund_request_id: UUID
    evidence_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    evidence_reference: str = Field(min_length=3, max_length=160)
    recorded_by_identity_id: UUID
    safe_metadata: dict[str, str] = Field(default_factory=dict)
    recorded_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("recorded_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Refund timestamps must be timezone-aware")
        return value.astimezone(UTC)
