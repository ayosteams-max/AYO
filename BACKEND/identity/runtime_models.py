import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from BACKEND.identity.models import AccountStatus, IdentityType


class ContactKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"


def normalize_contact(kind: ContactKind, value: str) -> str:
    normalized = value.strip()
    if kind is ContactKind.EMAIL:
        normalized = normalized.casefold()
        if (
            len(normalized) > 254
            or normalized.count("@") != 1
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("Invalid contact identifier")
    elif re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized) is None:
        raise ValueError("Phone number must use E.164 format")
    return normalized


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    contact_kind: ContactKind
    contact: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=12, max_length=128)]
    device_id: UUID
    device_category: Annotated[str, Field(min_length=1, max_length=32)] = "mobile"
    operating_system_family: Annotated[str, Field(min_length=1, max_length=32)]
    application_version: Annotated[str, Field(min_length=1, max_length=32)]

    @field_validator("contact")
    @classmethod
    def contact_is_valid(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        kind = data.get("contact_kind")
        return normalize_contact(ContactKind(kind), value) if kind else value


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    contact_kind: ContactKind
    contact: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=128)]
    device_id: UUID
    device_category: Annotated[str, Field(min_length=1, max_length=32)] = "mobile"
    operating_system_family: Annotated[str, Field(min_length=1, max_length=32)]
    application_version: Annotated[str, Field(min_length=1, max_length=32)]

    @field_validator("contact")
    @classmethod
    def contact_is_valid(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        kind = data.get("contact_kind")
        return normalize_contact(ContactKind(kind), value) if kind else value


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    refresh_token: Annotated[str, Field(min_length=64, max_length=256)]


class RecoveryPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    contact_kind: ContactKind
    contact: Annotated[str, Field(min_length=3, max_length=254)]

    @field_validator("contact")
    @classmethod
    def contact_is_valid(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        kind = data.get("contact_kind")
        return normalize_contact(ContactKind(kind), value) if kind else value


class VerificationPreparationRequest(RecoveryPreparationRequest):
    pass


class VerificationCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    challenge_id: UUID
    code: Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class VerificationPreparationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    challenge_id: UUID
    expires_at: datetime


class IdentityActivationProgress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity_id: UUID
    email_status: str | None = None
    phone_status: str | None = None
    activated: bool


class AuthenticationSessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity_id: UUID
    session_id: UUID
    identity_type: IdentityType
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    token_type: str = "Bearer"

    @field_validator("access_expires_at", "refresh_expires_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Token timestamps must be timezone-aware")
        return value.astimezone(UTC)


class PasswordCredentialRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity_id: UUID
    identity_type: IdentityType
    account_status: AccountStatus
    verifier: str
    scheme: str
