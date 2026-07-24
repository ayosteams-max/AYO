from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PartnerStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REVOKED = "revoked"


class CaseStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BUSINESS_OWNER_ASSISTED = "business_owner_assisted"
    OWNER_VERIFICATION_COMPLETED = "owner_verification_completed"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    APPROVED = "approved"
    RETURNED_FOR_CORRECTION = "returned_for_correction"
    REJECTED = "rejected"


class CaseAction(StrEnum):
    START = "start"
    RECORD_OWNER_ASSISTED = "record_owner_assisted"
    CONFIRM_OWNER_VERIFICATION = "confirm_owner_verification"
    SUBMIT_FOR_REVIEW = "submit_for_review"
    RESUME_CORRECTION = "resume_correction"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    RETURN = "return"
    REJECT = "reject"


class ConductEvidenceKind(StrEnum):
    TRAINING_COMPLETED = "training_completed"
    CODE_OF_CONDUCT_ACCEPTED = "code_of_conduct_accepted"
    QUALITY_OBSERVATION = "quality_observation"
    COMPLAINT_RECORDED = "complaint_recorded"
    TEMPORARY_SUSPENSION = "temporary_suspension"
    PERMANENT_REVOCATION = "permanent_revocation"


class ActivityKind(StrEnum):
    BUSINESS_VISITED = "business_visited"
    DRIVER_RECRUITED = "driver_recruited"
    COURIER_RECRUITED = "courier_recruited"
    VERIFICATION_COMPLETED = "verification_completed"
    ONBOARDING_COMPLETED = "onboarding_completed"
    QUALITY_CHECKED = "quality_checked"
    CATALOGUE_ASSISTED = "catalogue_assisted"
    PROFILE_ASSISTED = "profile_assisted"
    HOURS_ASSISTED = "hours_assisted"


class FieldPartner(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID = Field(default_factory=uuid4)
    public_partner_id: str = Field(pattern=r"^AYO-FP-[A-Z0-9]{8,20}$")
    identity_id: UUID
    photo_reference: str = Field(min_length=16, max_length=160)
    qr_reference_hash: str = Field(min_length=64, max_length=64)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    status: PartnerStatus = PartnerStatus.INACTIVE
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("field operations timestamps must be timezone-aware")
        return value.astimezone(UTC)


class PartnerRole(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    role_id: UUID = Field(default_factory=uuid4)
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    public_title: str = Field(min_length=2, max_length=100)
    allowed_activities: tuple[ActivityKind, ...]
    active: bool = True
    version: int = Field(default=1, ge=1)


class Territory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    territory_id: UUID = Field(default_factory=uuid4)
    market_code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9-]{2,12}$")
    region: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=2, max_length=120)
    active: bool = True
    version: int = Field(default=1, ge=1)


class PartnerAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assignment_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    role_id: UUID
    territory_id: UUID
    starts_at: datetime
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def assignment_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("assignment timestamps must be timezone-aware")
        return None if value is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "PartnerAssignment":
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("assignment end must follow start")
        return self


class AssistanceCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    territory_id: UUID
    subject_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    subject_id: UUID
    owner_identity_id: UUID | None = None
    capability_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    status: CaseStatus = CaseStatus.ASSIGNED
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def case_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("case timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ReviewChecklist(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    correct_business: bool
    correct_owner: bool
    required_verification_completed: bool
    required_documents_completed: bool
    no_duplicate_onboarding: bool
    no_representative_misconduct: bool
    business_readiness_evidence: bool

    def complete(self) -> bool:
        return all(self.model_dump().values())


class CaseEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    from_status: CaseStatus | None
    to_status: CaseStatus
    actor_identity_id: UUID
    actor_role: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,39}$")
    evidence_reference: str = Field(min_length=16, max_length=160)
    reason_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{1,62}$")
    checklist: ReviewChecklist | None = None
    case_version: int = Field(ge=1)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def evidence_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("case evidence timestamp must be timezone-aware")
        return value.astimezone(UTC)


class ConductEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    kind: ConductEvidenceKind
    evidence_reference: str = Field(min_length=16, max_length=160)
    recorded_by_identity_id: UUID
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def conduct_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("conduct timestamp must be timezone-aware")
        return value.astimezone(UTC)


class CaseQueue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    items: tuple[AssistanceCase, ...]
    next_cursor: UUID | None = None


class ManagementQualityDashboard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    territory_workload: int = Field(ge=0)
    review_workload: int = Field(ge=0)
    approved: int = Field(ge=0)
    returned: int = Field(ge=0)
    rejected: int = Field(ge=0)
    approval_rate_bps: int = Field(ge=0, le=10_000)


class FieldActivity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    activity_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    assignment_id: UUID
    case_id: UUID | None = None
    territory_id: UUID
    kind: ActivityKind
    subject_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    subject_id: UUID
    evidence_reference: str = Field(min_length=16, max_length=160)
    quality_status: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_.-]{1,62}$"
    )
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def activity_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("activity timestamp must be timezone-aware")
        return value.astimezone(UTC)


class PartnerDashboard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner: FieldPartner
    assignments: tuple[PartnerAssignment, ...]
    today_activities: int = Field(ge=0)
    completed_onboardings: int = Field(ge=0)
    pending_work: int = Field(ge=0)
    active_cases: int = Field(default=0, ge=0)
    pending_review: int = Field(default=0, ge=0)
    approved_cases: int = Field(default=0, ge=0)
    returned_cases: int = Field(default=0, ge=0)
    rejected_cases: int = Field(default=0, ge=0)
    future_earnings_placeholder: str = "Coming Soon"
