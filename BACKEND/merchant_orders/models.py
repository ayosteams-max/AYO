from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from BACKEND.ordering.models import OrderLineEvidence, OrderPricingEvidence, OrderState


class MerchantOrderAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class MerchantDecisionState(StrEnum):
    PENDING = "pending_merchant_decision"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "decision_window_expired"


class MerchantRejectionReason(StrEnum):
    ITEM_OR_MODIFIER_UNAVAILABLE = "item_or_modifier_unavailable"
    MERCHANT_CAPACITY_EXCEEDED = "merchant_capacity_exceeded"
    CLOSING_OR_CLOSED = "closing_or_closed"
    CANNOT_HONOR_CUSTOMER_INSTRUCTION = "cannot_honor_customer_instruction"
    TECHNICAL_OR_OPERATIONAL_ISSUE = "technical_or_operational_issue"
    SUSPECTED_DUPLICATE_ORDER = "suspected_duplicate_order"
    OTHER_REVIEW_REQUIRED = "other_review_required"


class MerchantDecisionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(pattern=r"^AYO_EAT_MERCHANT_DECISION_POLICY_V1$")
    version: int = Field(default=1, ge=1)
    maximum_window_seconds: int = Field(ge=1, le=300)


class MerchantStaffAuthority(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authority_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    merchant_location_id: UUID
    staff_identity_id: UUID
    authority_basis: str = Field(min_length=3, max_length=128)
    active: bool = True
    valid_from: datetime
    valid_until: datetime | None = None
    granted_by_identity_id: UUID
    revoked_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime

    @field_validator("valid_from", "valid_until", "revoked_at", "created_at")
    @classmethod
    def authority_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("authority timestamps must be timezone-aware")
        return None if value is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "MerchantStaffAuthority":
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("staff authority validity window is invalid")
        if self.revoked_at is not None and self.active:
            raise ValueError("revoked staff authority cannot remain active")
        return self


class MerchantDecisionCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_case_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    order_version: int = Field(ge=1)
    merchant_id: UUID
    merchant_location_id: UUID
    state: MerchantDecisionState = MerchantDecisionState.PENDING
    policy_name: str = Field(pattern=r"^AYO_EAT_MERCHANT_DECISION_POLICY_V1$")
    policy_version: int = Field(ge=1)
    window_started_at: datetime
    expires_at: datetime
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("window_started_at", "expires_at", "created_at", "updated_at")
    @classmethod
    def decision_case_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decision-case timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "MerchantDecisionCase":
        if self.expires_at <= self.window_started_at:
            raise ValueError("decision expiry must follow window start")
        return self


class MerchantDecisionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    decision_case_id: UUID
    order_id: UUID
    merchant_id: UUID
    merchant_location_id: UUID
    authenticated_subject_id: UUID | None = None
    merchant_owner_identity_id: UUID
    authority_basis: str = Field(min_length=3, max_length=128)
    result: MerchantDecisionState
    rejection_reason: MerchantRejectionReason | None = None
    policy_name: str = Field(pattern=r"^AYO_EAT_MERCHANT_DECISION_POLICY_V1$")
    policy_version: int = Field(ge=1)
    decided_at: datetime
    expires_at: datetime
    correlation_id: UUID
    causation_id: UUID
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    retention_class: str = Field(
        default="provisional_regulated_commerce",
        pattern=r"^provisional_regulated_commerce$",
    )

    @field_validator("decided_at", "expires_at")
    @classmethod
    def evidence_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decision-evidence timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def reason_matches_result(self) -> "MerchantDecisionEvidence":
        if (self.result is MerchantDecisionState.REJECTED) != (
            self.rejection_reason is not None
        ):
            raise ValueError("structured reason must exist only for rejection")
        return self


class RejectionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    order_id: UUID
    customer_reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,62}$", max_length=63)
    customer_message: str = Field(min_length=2, max_length=240)
    internal_merchant_note: str | None = Field(default=None, max_length=1000)
    decided_by_identity_id: UUID
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decision timestamp must be timezone-aware")
        return value.astimezone(UTC)


class OrderTimelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    merchant_id: UUID
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,62}$", max_length=63)
    from_state: OrderState | None
    to_state: OrderState
    actor_identity_id: UUID | None
    order_version: int = Field(ge=1)
    customer_reason_code: str | None = Field(default=None, max_length=63)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def event_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timeline timestamp must be timezone-aware")
        return value.astimezone(UTC)


class MerchantOrderRecord(BaseModel):
    """Merchant-safe projection: customer identity is deliberately excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    order_id: UUID
    merchant_id: UUID
    merchant_display_name: str
    state: OrderState
    lines: tuple[OrderLineEvidence, ...]
    pricing: OrderPricingEvidence
    evidence_hash: str
    version: int = Field(ge=1)
    created_at: datetime


class MerchantOrderView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    order: MerchantOrderRecord
    timeline: tuple[OrderTimelineEvent, ...]
    rejection: RejectionDecision | None = None

    @model_validator(mode="after")
    def decision_matches_state(self) -> "MerchantOrderView":
        if (self.order.state is OrderState.REJECTED) != (self.rejection is not None):
            raise ValueError("rejection evidence must match rejected state")
        return self
