from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MinorAmount = Annotated[int, Field(ge=1, le=10_000_000_000)]


class FinancialPostingSourceType(StrEnum):
    COMPLETED_PAYMENT = "completed_payment"
    APPROVED_REFUND = "approved_refund"
    SETTLEMENT_EVENT = "settlement_event"
    WALLET_ADJUSTMENT = "wallet_adjustment"


class FinancialPostingState(StrEnum):
    POSTED = "posted"


class FinancialPostingEntrySide(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class FinancialPostingLineCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    line_index: int = Field(ge=1, le=1024)
    account_id: UUID
    side: FinancialPostingEntrySide
    amount_minor: MinorAmount


class FinancialPostingCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: FinancialPostingSourceType
    source_id: UUID
    operation: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    lines: tuple[FinancialPostingLineCommand, ...]
    wallet_owner_identity_id: UUID
    wallet_amount_minor: MinorAmount
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID
    causation_id: UUID
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Financial posting timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_lines(self) -> "FinancialPostingCommand":
        if len(self.lines) < 2:
            raise ValueError("A posting command requires at least two lines")
        if len({item.line_index for item in self.lines}) != len(self.lines):
            raise ValueError("Posting command line_index values must be unique")
        if self.currency != "ETB":
            raise ValueError("Financial posting currently supports ETB only")
        return self


class FinancialPosting(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    posting_id: UUID = Field(default_factory=uuid4)
    source_type: FinancialPostingSourceType
    source_id: UUID
    operation: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    state: FinancialPostingState = FinancialPostingState.POSTED
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    total_debit_minor: MinorAmount
    total_credit_minor: MinorAmount
    actor_identity_id: UUID
    ledger_journal_id: UUID
    wallet_entry_id: UUID
    correlation_id: UUID
    causation_id: UUID
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Financial posting timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def balanced(self) -> "FinancialPosting":
        if self.currency != "ETB":
            raise ValueError("Financial posting currently supports ETB only")
        if self.total_debit_minor != self.total_credit_minor:
            raise ValueError("Financial posting must be balanced")
        return self


class FinancialPostingLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    posting_line_id: UUID = Field(default_factory=uuid4)
    posting_id: UUID
    line_index: int = Field(ge=1, le=1024)
    account_id: UUID
    side: FinancialPostingEntrySide
    amount_minor: MinorAmount
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class FinancialPostingResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    posting: FinancialPosting
    lines: tuple[FinancialPostingLine, ...]
