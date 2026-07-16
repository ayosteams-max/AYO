from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReasonCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)]


class OnboardingState(StrEnum):
    DRAFT = "draft"
    CONTACT_VERIFICATION_PENDING = "contact_verification_pending"
    IDENTITY_EVIDENCE_PENDING = "identity_evidence_pending"
    DOCUMENT_REVIEW_PENDING = "document_review_pending"
    VEHICLE_EVIDENCE_PENDING = "vehicle_evidence_pending"
    OPERATIONS_REVIEW_PENDING = "operations_review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    REVERIFICATION_REQUIRED = "reverification_required"
    APPEAL_PENDING = "appeal_pending"


class EvidenceType(StrEnum):
    LEGAL_IDENTITY = "legal_identity"
    DRIVER_LICENCE = "driver_licence"
    VEHICLE_REGISTRATION = "vehicle_registration"
    INSURANCE = "insurance"
    INSPECTION = "inspection"
    OWNERSHIP_AUTHORIZATION = "ownership_authorization"


class EvidenceStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class VehicleApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class AuthorizationStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    REVOKED = "revoked"
    EXPIRED = "expired"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    REVERIFICATION_REQUIRED = "reverification_required"


class OnboardingCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: UUID = Field(default_factory=uuid4)
    driver_identity_id: UUID
    state: OnboardingState = OnboardingState.DRAFT
    policy_version: ReasonCode
    version: Annotated[int, Field(ge=1)] = 1
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    appeal_of_case_id: UUID | None = None

    @field_validator("created_at", "updated_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Onboarding timestamps must be timezone-aware")
        return value.astimezone(UTC)


class DocumentEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    driver_identity_id: UUID
    vehicle_id: UUID | None = None
    evidence_type: EvidenceType
    immutable_reference: Annotated[str, Field(min_length=8, max_length=256)]
    issuing_authority_code: ReasonCode
    document_reference_hash: bytes = Field(min_length=32, max_length=32)
    issue_date: date
    expiry_date: date
    status: EvidenceStatus = EvidenceStatus.SUBMITTED
    policy_version: ReasonCode
    reviewer_identity_id: UUID | None = None
    reason_codes: tuple[ReasonCode, ...] = ()
    replaces_evidence_id: UUID | None = None
    superseded_by_evidence_id: UUID | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("submitted_at", "reviewed_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_period(self) -> "DocumentEvidence":
        if self.expiry_date <= self.issue_date:
            raise ValueError("Evidence expiry must follow issue date")
        if self.status in {
            EvidenceStatus.APPROVED,
            EvidenceStatus.REJECTED,
        } and (self.reviewer_identity_id is None or self.reviewed_at is None):
            raise ValueError("Reviewed evidence requires reviewer and timestamp")
        return self


class Vehicle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    vehicle_id: UUID = Field(default_factory=uuid4)
    canonical_reference_hash: bytes = Field(min_length=32, max_length=32)
    category: ReasonCode
    accessibility_capabilities: tuple[ReasonCode, ...] = ()
    airport_standard_inputs: tuple[ReasonCode, ...] = ()
    airport_premium_inputs: tuple[ReasonCode, ...] = ()
    approval_status: VehicleApprovalStatus = VehicleApprovalStatus.PENDING
    policy_version: ReasonCode
    version: Annotated[int, Field(ge=1)] = 1
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Vehicle timestamps must be timezone-aware")
        return value.astimezone(UTC)


class DriverVehicleAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authorization_id: UUID = Field(default_factory=uuid4)
    driver_identity_id: UUID
    vehicle_id: UUID
    status: AuthorizationStatus = AuthorizationStatus.PENDING
    policy_version: ReasonCode
    effective_at: datetime
    expires_at: datetime
    reason_codes: tuple[ReasonCode, ...] = ()
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("effective_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Authorization timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_period(self) -> "DriverVehicleAuthorization":
        if self.expires_at <= self.effective_at:
            raise ValueError("Authorization expiry must follow effective time")
        return self


class EligibilityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_version: ReasonCode
    required_evidence: frozenset[EvidenceType]
    inspection_required: bool = True
    expiring_soon_days: Annotated[int, Field(ge=1, le=180)] = 30


class EligibilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_id: UUID = Field(default_factory=uuid4)
    driver_identity_id: UUID
    vehicle_id: UUID | None = None
    policy_version: ReasonCode
    status: EligibilityStatus
    reason_codes: tuple[ReasonCode, ...]
    missing_evidence: tuple[EvidenceType, ...]
    expires_at: datetime | None
    recomputed_at: datetime
    audit_reference: UUID

    @field_validator("expires_at", "recomputed_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Eligibility timestamps must be timezone-aware")
        return value.astimezone(UTC)
