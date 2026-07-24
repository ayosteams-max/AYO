from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CanonicalCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,126}$")]
OpaqueReference = Annotated[str, Field(min_length=8, max_length=128)]


class AccessChannel(StrEnum):
    MOBILE_APP = "mobile_app"
    VOICE_ASSISTANCE = "voice_assistance"
    SMS = "sms"
    USSD = "ussd"
    BUSINESS_PORTAL = "business_portal"
    SUPPORT_TOOL = "support_tool"


class InteractionMethod(StrEnum):
    SELF_SERVICE = "self_service"
    DELEGATED = "delegated"
    SUPPORT_ASSISTED = "support_assisted"
    AUTOMATED_ASSISTED = "automated_assisted"


class ProvenancePurpose(StrEnum):
    INITIATION = "initiation"
    CONTINUATION = "continuation"
    CORRECTION = "correction"
    LEGACY_VERIFIED = "legacy_verified"


class DeviceCapabilityClass(StrEnum):
    RICH_SCREEN = "rich_screen"
    LIMITED_SCREEN = "limited_screen"
    VOICE_ONLY = "voice_only"
    TEXT_CAPABLE_BASIC_PHONE = "text_capable_basic_phone"
    ASSISTED_CHANNEL = "assisted_channel"
    UNKNOWN = "unknown"


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    ASSISTED_ONLY = "assisted_only"
    DEGRADED = "degraded"
    RETIRED = "retired"


class SourceAdapter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    adapter_id: UUID
    adapter_code: CanonicalCode
    adapter_version: Annotated[int, Field(ge=1)]
    channel: AccessChannel
    active: bool
    created_at: datetime


class ChannelActionCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: UUID
    target_domain: CanonicalCode
    command_type: CanonicalCode
    channel: AccessChannel
    adapter_id: UUID
    adapter_version: Annotated[int, Field(ge=1)]
    state: CapabilityState
    effective_from: datetime
    effective_until: datetime | None = None
    version: Annotated[int, Field(ge=1)] = 1
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_period(self) -> "ChannelActionCapability":
        if (
            self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("effective_until must follow effective_from")
        return self


class ContinuityReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    continuity_id: UUID
    reference_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    authenticated_account_id: UUID
    acting_subject_id: UUID
    target_domain: CanonicalCode
    target_type: CanonicalCode
    target_id: OpaqueReference
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_expiry(self) -> "ContinuityReference":
        if self.expires_at <= self.created_at:
            raise ValueError("Continuity reference must expire after creation")
        return self


class InteractionProvenanceEnvelope(BaseModel):
    """Closed, transient metadata accepted from a registered adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    purpose: ProvenancePurpose
    target_domain: CanonicalCode
    target_type: CanonicalCode
    target_id: OpaqueReference
    target_version: Annotated[int, Field(ge=1)]
    command_type: CanonicalCode
    channel: AccessChannel
    interaction_method: InteractionMethod
    adapter_id: UUID
    adapter_version: Annotated[int, Field(ge=1)]
    initiating_subject_id: UUID | None = None
    authenticated_account_id: UUID
    authenticated_subject_id: UUID
    acting_subject_id: UUID
    requester_subject_id: UUID | None = None
    passenger_subject_id: UUID | None = None
    delegated_authority_reference: OpaqueReference | None = None
    sponsor_organization_id: UUID | None = None
    support_agent_subject_id: UUID | None = None
    support_agent_account_id: UUID | None = None
    response_channel_preference: AccessChannel | None = None
    interaction_language_reference: CanonicalCode | None = None
    interface_accommodation_references: tuple[CanonicalCode, ...] = ()
    device_capability: DeviceCapabilityClass = DeviceCapabilityClass.UNKNOWN
    interaction_reference: OpaqueReference | None = None
    continuity_reference: OpaqueReference | None = Field(default=None, exclude=True)
    continuity_id: UUID | None = Field(default=None, exclude=True)
    supersedes_provenance_id: UUID | None = None
    correction_classification: CanonicalCode | None = None

    @model_validator(mode="after")
    def validate_roles_and_lineage(self) -> "InteractionProvenanceEnvelope":
        if len(self.interface_accommodation_references) > 8:
            raise ValueError("At most eight interface accommodations are permitted")
        if len(set(self.interface_accommodation_references)) != len(
            self.interface_accommodation_references
        ):
            raise ValueError("Interface accommodations must be unique")
        if self.interaction_method is InteractionMethod.DELEGATED:
            if self.delegated_authority_reference is None:
                raise ValueError("Delegated interaction requires authority reference")
        elif self.delegated_authority_reference is not None:
            raise ValueError("Authority reference is permitted only for delegation")
        support_fields = (
            self.support_agent_subject_id,
            self.support_agent_account_id,
        )
        if self.interaction_method is InteractionMethod.SUPPORT_ASSISTED:
            if any(value is None for value in support_fields):
                raise ValueError(
                    "Support-assisted interaction requires dual attribution"
                )
        elif any(value is not None for value in support_fields):
            raise ValueError(
                "Support identity is permitted only for assisted interaction"
            )
        if self.purpose is ProvenancePurpose.INITIATION:
            if (
                self.continuity_reference is not None
                or self.continuity_id is not None
                or self.supersedes_provenance_id is not None
                or self.correction_classification is not None
            ):
                raise ValueError("Initiation cannot continue or correct prior evidence")
        elif self.purpose is ProvenancePurpose.CONTINUATION:
            if self.continuity_reference is None and self.continuity_id is None:
                raise ValueError("Continuation requires explicit continuity reference")
            if (
                self.supersedes_provenance_id is not None
                or self.correction_classification is not None
            ):
                raise ValueError("Continuation cannot supersede provenance")
        elif self.purpose is ProvenancePurpose.CORRECTION and (
            self.supersedes_provenance_id is None
            or self.correction_classification is None
        ):
            raise ValueError("Correction requires superseded record and classification")
        return self


class InteractionProvenanceRecord(InteractionProvenanceEnvelope):
    provenance_id: UUID
    schema_version: Annotated[int, Field(ge=1)] = 1
    accepted_at: datetime
    correlation_id: UUID
    causation_id: UUID | None = None
    command_id: UUID
    request_id: UUID
    interaction_idempotency_key: OpaqueReference

    @field_validator("accepted_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("accepted_at must be timezone-aware")
        return value.astimezone(UTC)
