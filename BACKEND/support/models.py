import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequesterType(StrEnum):
    ANONYMOUS = "anonymous"
    RIDER = "rider"
    DRIVER = "driver"
    MERCHANT = "merchant"
    STAFF = "staff"
    SERVICE = "service"


class SupportChannel(StrEnum):
    IN_APP_CHAT = "in_app_chat"
    VOICE_CALL = "voice_call"
    VOICE_MESSAGE = "voice_message"
    WEB_CHAT = "web_chat"
    SMS = "sms"
    EMAIL = "email"
    MESSAGING_PLATFORM = "messaging_platform"


class SupportCategory(StrEnum):
    RIDE_STATUS = "ride_status"
    DRIVER_NOT_ARRIVING = "driver_not_arriving"
    RIDER_NOT_PRESENT = "rider_not_present"
    CANCELLATION = "cancellation"
    FARE_EXPLANATION = "fare_explanation"
    PAYMENT_STATUS = "payment_status"
    PAYOUT_STATUS = "payout_status"
    LOST_ITEM = "lost_item"
    ACCOUNT_ACCESS = "account_access"
    IDENTITY_VERIFICATION = "identity_verification"
    SAFETY_CONCERN = "safety_concern"
    FRAUD_CONCERN = "fraud_concern"
    TECHNICAL_PROBLEM = "technical_problem"
    COMPLAINT = "complaint"
    ACCESSIBILITY_HELP = "accessibility_help"
    GENERAL_INFORMATION = "general_information"


class SupportPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class RiskClassification(StrEnum):
    ROUTINE = "routine"
    SENSITIVE = "sensitive"
    SAFETY = "safety"
    FRAUD = "fraud"
    FINANCIAL = "financial"
    IDENTITY = "identity"
    LEGAL = "legal"
    ACCOUNT_TAKEOVER = "account_takeover"


class SupportStatus(StrEnum):
    NEW = "new"
    GATHERING_INFORMATION = "gathering_information"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    WAITING_FOR_INTERNAL_TEAM = "waiting_for_internal_team"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


ALLOWED_SUPPORT_TRANSITIONS: dict[SupportStatus, frozenset[SupportStatus]] = {
    SupportStatus.NEW: frozenset(
        {
            SupportStatus.GATHERING_INFORMATION,
            SupportStatus.IN_PROGRESS,
            SupportStatus.ESCALATED,
            SupportStatus.CANCELLED,
        }
    ),
    SupportStatus.GATHERING_INFORMATION: frozenset(
        {
            SupportStatus.IN_PROGRESS,
            SupportStatus.WAITING_FOR_CUSTOMER,
            SupportStatus.ESCALATED,
            SupportStatus.CANCELLED,
        }
    ),
    SupportStatus.IN_PROGRESS: frozenset(
        {
            SupportStatus.WAITING_FOR_CUSTOMER,
            SupportStatus.WAITING_FOR_INTERNAL_TEAM,
            SupportStatus.ESCALATED,
            SupportStatus.RESOLVED,
            SupportStatus.CANCELLED,
        }
    ),
    SupportStatus.WAITING_FOR_CUSTOMER: frozenset(
        {SupportStatus.IN_PROGRESS, SupportStatus.ESCALATED, SupportStatus.CANCELLED}
    ),
    SupportStatus.WAITING_FOR_INTERNAL_TEAM: frozenset(
        {SupportStatus.IN_PROGRESS, SupportStatus.ESCALATED, SupportStatus.CANCELLED}
    ),
    SupportStatus.ESCALATED: frozenset(
        {
            SupportStatus.IN_PROGRESS,
            SupportStatus.WAITING_FOR_INTERNAL_TEAM,
            SupportStatus.RESOLVED,
        }
    ),
    SupportStatus.RESOLVED: frozenset(
        {SupportStatus.CLOSED, SupportStatus.IN_PROGRESS}
    ),
    SupportStatus.CLOSED: frozenset(),
    SupportStatus.CANCELLED: frozenset(),
}


class SupportQueue(StrEnum):
    GENERAL = "general"
    SAFETY = "safety"
    FRAUD = "fraud"
    FINANCE = "finance"
    IDENTITY = "identity"
    LEGAL = "legal"


class RetentionClassification(StrEnum):
    ROUTINE_SUPPORT = "routine_support"
    SENSITIVE_SUPPORT = "sensitive_support"
    SAFETY_EVIDENCE = "safety_evidence"
    FINANCIAL_DISPUTE = "financial_dispute"
    IDENTITY_SECURITY = "identity_security"
    LEGAL_HOLD_CANDIDATE = "legal_hold_candidate"


class SupportCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID = Field(default_factory=uuid4)
    public_reference: UUID = Field(default_factory=uuid4)
    requester_identity_id: UUID | None = None
    requester_type: RequesterType
    source_channel: SupportChannel
    category: SupportCategory
    priority: SupportPriority = SupportPriority.NORMAL
    risk_classification: RiskClassification = RiskClassification.ROUTINE
    status: SupportStatus = SupportStatus.NEW
    assigned_queue: SupportQueue = SupportQueue.GENERAL
    assigned_human_identity_id: UUID | None = None
    ai_service_identity_id: UUID | None = None
    related_ride_reference: (
        Annotated[str, Field(min_length=1, max_length=128)] | None
    ) = None
    related_payment_status_reference: (
        Annotated[str, Field(min_length=1, max_length=128)] | None
    ) = None
    correlation_id: UUID
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    escalation_reason: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")] | None
    ) = None
    resolution_category: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")] | None
    ) = None
    retention_classification: RetentionClassification
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "updated_at", "resolved_at", "closed_at")
    @classmethod
    def timestamps_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Support-case timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def lifecycle_consistent(self) -> "SupportCase":
        if self.requester_type is RequesterType.ANONYMOUS:
            if self.requester_identity_id is not None:
                raise ValueError("Anonymous requester cannot carry an identity")
        elif self.requester_identity_id is None:
            raise ValueError("Authenticated requester requires an identity")
        if self.status is SupportStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("Resolved case requires resolved_at")
        if self.status is SupportStatus.CLOSED and (
            self.resolved_at is None or self.closed_at is None
        ):
            raise ValueError("Closed case requires resolved_at and closed_at")
        if self.priority is SupportPriority.EMERGENCY and (
            self.assigned_queue is not SupportQueue.SAFETY
            or self.status is not SupportStatus.ESCALATED
        ):
            raise ValueError("Emergency case must be immediately escalated to safety")
        restricted_queue = {
            RiskClassification.SAFETY: SupportQueue.SAFETY,
            RiskClassification.FRAUD: SupportQueue.FRAUD,
            RiskClassification.FINANCIAL: SupportQueue.FINANCE,
            RiskClassification.IDENTITY: SupportQueue.IDENTITY,
            RiskClassification.ACCOUNT_TAKEOVER: SupportQueue.IDENTITY,
            RiskClassification.LEGAL: SupportQueue.LEGAL,
        }.get(self.risk_classification)
        if restricted_queue is not None and (
            self.assigned_queue is not restricted_queue
            or self.status is not SupportStatus.ESCALATED
        ):
            raise ValueError("High-risk case must be immediately escalated")
        return self

    def transition(
        self,
        target: SupportStatus,
        *,
        at: datetime,
        escalation_reason: str | None = None,
        resolution_category: str | None = None,
    ) -> "SupportCase":
        if target not in ALLOWED_SUPPORT_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid support transition: {self.status}->{target}")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Support transition time must be timezone-aware")
        updates: dict[str, object] = {
            "status": target,
            "updated_at": at.astimezone(UTC),
        }
        if target is SupportStatus.ESCALATED:
            if escalation_reason is None:
                raise ValueError("Escalation requires a safe reason")
            updates["escalation_reason"] = escalation_reason
        if target is SupportStatus.RESOLVED:
            if resolution_category is None:
                raise ValueError("Resolution requires a category")
            updates.update(
                resolved_at=at.astimezone(UTC),
                resolution_category=resolution_category,
            )
        if target is SupportStatus.CLOSED:
            updates["closed_at"] = at.astimezone(UTC)
        return SupportCase.model_validate({**self.model_dump(), **updates})


class MessageVisibility(StrEnum):
    CUSTOMER_VISIBLE = "customer_visible"
    INTERNAL_NOTE = "internal_note"


SENSITIVE_CONTENT = re.compile(
    r"(?i)(authorization\s*:\s*bearer|access[_ -]?token|refresh[_ -]?token|"
    r"otp\s*[:=]|password\s*[:=]|cvv\s*[:=]|private[_ -]?key)"
)


class SupportMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    message_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    author_identity_id: UUID | None = None
    visibility: MessageVisibility
    language_tag: Annotated[
        str, Field(pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=35)
    ]
    content: Annotated[str, Field(min_length=1, max_length=2_000)]
    redaction_applied: bool = False
    created_at: datetime

    @field_validator("content")
    @classmethod
    def reject_sensitive_content(cls, value: str) -> str:
        if SENSITIVE_CONTENT.search(value):
            raise ValueError("Support content contains prohibited sensitive material")
        return value

    @field_validator("created_at")
    @classmethod
    def created_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Message creation time must be timezone-aware")
        return value.astimezone(UTC)


class SupportEventType(StrEnum):
    CREATED = "created"
    VIEWED = "viewed"
    UPDATED = "updated"
    INFORMATION_REQUESTED = "information_requested"
    ASSIGNED = "assigned"
    ESCALATED = "escalated"
    HUMAN_TAKEOVER = "human_takeover"
    AI_GUIDANCE_PROVIDED = "ai_guidance_provided"
    RECOMMENDATION_CREATED = "recommendation_created"
    RECOMMENDATION_APPROVED = "recommendation_approved"
    RECOMMENDATION_DENIED = "recommendation_denied"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ACCESS_DENIED = "access_denied"
    REDACTION_APPLIED = "redaction_applied"


SAFE_EVENT_METADATA_KEYS = frozenset(
    {"state_from", "state_to", "queue", "category", "action", "outcome"}
)


class SupportCaseEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    event_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    event_type: SupportEventType
    actor_identity_id: UUID | None = None
    actor_type: RequesterType
    correlation_id: UUID
    safe_metadata: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime

    @field_validator("safe_metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) - SAFE_EVENT_METADATA_KEYS:
            raise ValueError("Support event metadata contains a prohibited field")
        if len(value) > 6 or any(len(item) > 128 for item in value.values()):
            raise ValueError("Support event metadata exceeds its bounds")
        return value

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Support event time must be timezone-aware")
        return value.astimezone(UTC)


class SupportAIInteraction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    interaction_id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    case_id: UUID
    ai_service_identity_id: UUID
    model_reference: Annotated[str, Field(min_length=1, max_length=63)] | None = None
    model_version_reference: (
        Annotated[str, Field(min_length=1, max_length=63)] | None
    ) = None
    confidence_band: Annotated[str, Field(pattern=r"^(unknown|low|medium|high)$")]
    action_category: Annotated[str, Field(min_length=1, max_length=63)]
    escalation_reason: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")] | None
    ) = None
    human_takeover_at: datetime | None = None
    correlation_id: UUID
    safe_outcome_category: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]
    created_at: datetime

    @field_validator("created_at", "human_takeover_at")
    @classmethod
    def interaction_times_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("AI interaction time must be timezone-aware")
        return value.astimezone(UTC)
