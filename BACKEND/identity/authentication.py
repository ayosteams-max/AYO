from datetime import UTC, datetime
from enum import StrEnum
from hmac import compare_digest, digest
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChallengePurpose(StrEnum):
    PHONE_OTP = "phone_otp"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"  # nosec B105 - public challenge-purpose label
    ACCOUNT_RECOVERY = "account_recovery"
    STEP_UP = "step_up"


class AuthenticationChallenge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    challenge_id: UUID = Field(default_factory=uuid4)
    method_id: UUID | None = None
    purpose: ChallengePurpose
    verifier: Annotated[bytes, Field(min_length=32, max_length=64)]
    expires_at: datetime
    consumed_at: datetime | None = None
    attempt_count: Annotated[int, Field(ge=0)] = 0
    max_attempts: Annotated[int, Field(ge=1, le=10)] = 5
    created_at: datetime

    @field_validator("expires_at", "consumed_at", "created_at")
    @classmethod
    def aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Challenge timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_lifetime(self) -> "AuthenticationChallenge":
        if self.expires_at <= self.created_at:
            raise ValueError("Challenge expiry must follow creation")
        return self


class ChallengeProtector(Protocol):
    def protect(self, challenge_id: UUID, secret: str) -> bytes: ...

    def matches(self, challenge_id: UUID, secret: str, verifier: bytes) -> bool: ...


class HmacChallengeProtector:
    """Requires externally managed key material; no production key is provided."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("Challenge protection key must be at least 32 bytes")
        self._key = key

    def protect(self, challenge_id: UUID, secret: str) -> bytes:
        if not secret or len(secret) > 128:
            raise ValueError("Challenge response length is invalid")
        return digest(self._key, challenge_id.bytes + secret.encode(), "sha256")

    def matches(self, challenge_id: UUID, secret: str, verifier: bytes) -> bool:
        return compare_digest(self.protect(challenge_id, secret), verifier)
