from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IdentityType(StrEnum):
    ANONYMOUS = "anonymous"
    RIDER = "rider"
    DRIVER = "driver"
    STAFF = "staff"
    ADMINISTRATOR = "administrator"
    SERVICE = "service"
    MERCHANT = "merchant"
    SERVICE_PROVIDER = "service_provider"


class AccountStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOCKED = "locked"
    DISABLED = "disabled"
    RECOVERY_PENDING = "recovery_pending"
    DELETION_PENDING = "deletion_pending"


ALLOWED_STATUS_TRANSITIONS: dict[AccountStatus, frozenset[AccountStatus]] = {
    AccountStatus.PENDING: frozenset(
        {AccountStatus.ACTIVE, AccountStatus.DISABLED, AccountStatus.DELETION_PENDING}
    ),
    AccountStatus.ACTIVE: frozenset(
        {
            AccountStatus.SUSPENDED,
            AccountStatus.LOCKED,
            AccountStatus.DISABLED,
            AccountStatus.RECOVERY_PENDING,
            AccountStatus.DELETION_PENDING,
        }
    ),
    AccountStatus.SUSPENDED: frozenset(
        {AccountStatus.ACTIVE, AccountStatus.DISABLED, AccountStatus.RECOVERY_PENDING}
    ),
    AccountStatus.LOCKED: frozenset(
        {AccountStatus.ACTIVE, AccountStatus.DISABLED, AccountStatus.RECOVERY_PENDING}
    ),
    AccountStatus.DISABLED: frozenset({AccountStatus.ACTIVE}),
    AccountStatus.RECOVERY_PENDING: frozenset(
        {AccountStatus.ACTIVE, AccountStatus.LOCKED, AccountStatus.DISABLED}
    ),
    AccountStatus.DELETION_PENDING: frozenset({AccountStatus.ACTIVE}),
}


class AuthenticationMethodType(StrEnum):
    PHONE_OTP = "phone_otp"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD = "password"  # nosec B105 - public authentication-method label
    PASSKEY = "passkey"
    RECOVERY_CODE = "recovery_code"
    STAFF_MFA = "staff_mfa"
    SERVICE_CREDENTIAL = "service_credential"


class AssuranceLevel(StrEnum):
    BASIC = "basic"
    MULTI_FACTOR = "multi_factor"
    PHISHING_RESISTANT = "phishing_resistant"


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identity_id: UUID = Field(default_factory=uuid4)
    public_id: UUID = Field(default_factory=uuid4)
    identity_type: IdentityType
    status: AccountStatus = AccountStatus.PENDING
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Identity timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def transition(self, target: AccountStatus, *, at: datetime) -> "Identity":
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Account-status transition time must be timezone-aware")
        if target not in ALLOWED_STATUS_TRANSITIONS[self.status]:
            raise ValueError(
                f"Invalid account-status transition: {self.status}->{target}"
            )
        return self.model_copy(
            update={"status": target, "updated_at": at.astimezone(UTC)}
        )


class AccessTokenClaims(BaseModel):
    """Validated claims contract; token encoding/signing is provider-neutral."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    token_id: UUID = Field(default_factory=uuid4)
    identity_id: UUID
    session_id: UUID
    identity_type: IdentityType
    assurance_level: AssuranceLevel
    issued_at: datetime
    expires_at: datetime
    not_before: datetime
    audience: Annotated[str, Field(min_length=1, max_length=63)]
    issuer: Annotated[str, Field(min_length=1, max_length=63)]
    key_id: Annotated[str, Field(min_length=1, max_length=63)]

    @field_validator("issued_at", "expires_at", "not_before")
    @classmethod
    def token_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Token timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def short_lived(self) -> "AccessTokenClaims":
        if self.expires_at <= self.issued_at:
            raise ValueError("Access token expiry must follow issuance")
        if self.expires_at - self.issued_at > timedelta(minutes=15):
            raise ValueError("Access token lifetime exceeds 15 minutes")
        return self

    def valid_at(self, now: datetime, *, clock_skew_seconds: int = 30) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Token validation time must be timezone-aware")
        if not 0 <= clock_skew_seconds <= 120:
            raise ValueError("Clock skew must be between 0 and 120 seconds")
        skew = timedelta(seconds=clock_skew_seconds)
        instant = now.astimezone(UTC)
        return self.not_before - skew <= instant < self.expires_at + skew


SAFE_AUTHENTICATION_FAILURE = "Authentication could not be completed."
