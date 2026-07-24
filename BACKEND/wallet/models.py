from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MinorAmount = Annotated[int, Field(ge=0, le=10_000_000_000)]


class WalletEntryType(StrEnum):
    PENDING_CREDIT = "pending_credit"
    PENDING_RELEASE = "pending_release"
    PENDING_REVERSAL = "pending_reversal"
    AVAILABLE_CREDIT = "available_credit"
    AVAILABLE_DEBIT = "available_debit"


class WalletAuthoritativeSourceType(StrEnum):
    LEDGER_JOURNAL = "ledger_journal"
    PAYMENT_ATTEMPT = "payment_attempt"
    REFUND_REQUEST = "refund_request"
    SETTLEMENT_BATCH = "settlement_batch"


class WalletAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wallet_account_id: UUID = Field(default_factory=uuid4)
    owner_identity_id: UUID
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    available_minor: MinorAmount = 0
    pending_minor: MinorAmount = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Wallet timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_chronology(self) -> "WalletAccount":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class WalletLineageEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wallet_entry_id: UUID = Field(default_factory=uuid4)
    wallet_account_id: UUID
    authoritative_source_type: WalletAuthoritativeSourceType
    authoritative_source_id: UUID
    entry_type: WalletEntryType
    amount_minor: MinorAmount
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    resulting_available_minor: MinorAmount
    resulting_pending_minor: MinorAmount
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    recorded_by_identity_id: UUID
    recorded_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @field_validator("recorded_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Wallet timestamps must be timezone-aware")
        return value.astimezone(UTC)
