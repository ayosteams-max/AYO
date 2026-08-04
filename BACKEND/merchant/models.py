from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MerchantKind(StrEnum):
    INDIVIDUAL = "individual"
    COMPANY = "company"
    FRANCHISE = "franchise"


class OnboardingSource(StrEnum):
    SELF = "self"
    ASSISTED = "assisted"
    REPRESENTATIVE = "representative"


class MerchantState(StrEnum):
    DRAFT = "draft"
    VERIFICATION_PENDING = "verification_pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"


class VerificationKind(StrEnum):
    IDENTITY = "identity"
    BUSINESS_LICENCE = "business_licence"
    TAX_REGISTRATION = "tax_registration"
    BANK_OR_PAYMENT = "bank_or_payment"
    FOOD_LICENCE = "food_licence"


class VerificationState(StrEnum):
    REQUIRED = "required"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CatalogueKind(StrEnum):
    FOOD = "food"
    RETAIL = "retail"
    PHARMACY = "pharmacy"
    SERVICE = "service"
    DIGITAL = "digital"


class CatalogueItemState(StrEnum):
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"
    ARCHIVED = "archived"


class MerchantProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant_id: UUID = Field(default_factory=uuid4)
    owner_identity_id: UUID
    legal_name: str = Field(min_length=2, max_length=160)
    display_name: str = Field(min_length=2, max_length=120)
    kind: MerchantKind
    onboarding_source: OnboardingSource
    assisted_by_identity_id: UUID | None = None
    state: MerchantState = MerchantState.DRAFT
    capability_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)
    market_code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9-]{2,12}$", max_length=15)
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("merchant timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def assistance_is_explicit(self) -> "MerchantProfile":
        assisted = self.onboarding_source is not OnboardingSource.SELF
        if assisted != (self.assisted_by_identity_id is not None):
            raise ValueError("assisted onboarding requires a representative identity")
        if self.assisted_by_identity_id == self.owner_identity_id:
            raise ValueError("owner cannot be recorded as onboarding representative")
        return self


class MerchantBranch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    branch_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    name: str = Field(min_length=2, max_length=120)
    address_label: str = Field(min_length=2, max_length=240)
    timezone: str = Field(default="Africa/Addis_Ababa", min_length=3, max_length=63)
    operating_hours: dict[str, str] = Field(default_factory=dict)
    active: bool = True
    created_at: datetime


class VerificationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    kind: VerificationKind
    state: VerificationState
    opaque_reference: str = Field(min_length=16, max_length=160)
    expires_at: datetime | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by_identity_id: UUID | None = None
    reason_code: str | None = Field(default=None, max_length=63)

    @field_validator("expires_at", "submitted_at", "reviewed_at")
    @classmethod
    def evidence_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("verification timestamps must be timezone-aware")
        return None if value is None else value.astimezone(UTC)


class PartnerProgram(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    program_id: UUID = Field(default_factory=uuid4)
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)
    badge_label: str = Field(min_length=2, max_length=80)
    capability_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)
    market_code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9-]{2,12}$", max_length=15)
    opens_at: datetime
    closes_at: datetime
    participant_limit: int | None = Field(default=None, ge=1, le=10_000_000)
    benefit_configuration: dict[str, str] = Field(default_factory=dict)
    active: bool = True
    version: int = Field(default=1, ge=1)

    @field_validator("opens_at", "closes_at")
    @classmethod
    def program_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("program timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def window(self) -> "PartnerProgram":
        if self.closes_at <= self.opens_at:
            raise ValueError("program closes_at must follow opens_at")
        return self


class ProgramEnrollment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    enrollment_id: UUID = Field(default_factory=uuid4)
    program_id: UUID
    merchant_id: UUID
    enrolled_at: datetime


class CatalogueItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    branch_id: UUID | None = None
    kind: CatalogueKind
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    category_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63)
    state: CatalogueItemState = CatalogueItemState.DRAFT
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class MerchantDashboard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant: MerchantProfile
    branch_count: int
    verification_complete: int
    verification_required: int
    catalogue_ready: int
    catalogue_total: int
    onboarding_percent: int = Field(ge=0, le=100)
    verification_percent: int = Field(ge=0, le=100)
    catalogue_percent: int = Field(ge=0, le=100)
    store_ready: bool
    program_badges: tuple[str, ...]
    orders_placeholder: str = "Coming Soon"
    analytics_placeholder: str = "Coming Soon"
