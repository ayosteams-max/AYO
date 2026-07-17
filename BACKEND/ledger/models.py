from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Minor = Annotated[int, Field(ge=1, le=10_000_000_000)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class LedgerAccountClass(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    REVENUE = "revenue"
    EXPENSE = "expense"
    EQUITY = "equity"
    CLEARING = "clearing"


class LedgerEntrySide(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class LedgerBook(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    book_id: UUID = Field(default_factory=uuid4)
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    description: str = Field(min_length=3, max_length=240)
    base_currency: Currency
    created_at: datetime
    archived_at: datetime | None = None

    @field_validator("created_at", "archived_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ledger timestamps must be timezone-aware")
        return value.astimezone(UTC)


class LedgerAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: UUID = Field(default_factory=uuid4)
    book_id: UUID
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    name: str = Field(min_length=3, max_length=160)
    account_class: LedgerAccountClass
    normal_side: LedgerEntrySide
    currency: Currency
    created_at: datetime
    archived_at: datetime | None = None

    @field_validator("created_at", "archived_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ledger timestamps must be timezone-aware")
        return value.astimezone(UTC)


class LedgerTraceability(BaseModel):
    """Immutable lineage from ride/pricing through the ledger journal."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_request_id: UUID
    dispatch_handoff_id: UUID
    assignment_id: UUID
    active_ride_id: UUID
    fare_estimate_id: UUID
    fare_calculation_id: UUID
    predecessor_ledger_journal_id: UUID | None = None
    wallet_id: UUID | None = None
    settlement_id: UUID | None = None
    driver_payout_id: UUID | None = None
    rider_payment_id: UUID | None = None
    refund_id: UUID | None = None
    promotion_id: UUID | None = None
    referral_id: UUID | None = None
    loyalty_id: UUID | None = None
    tax_record_id: UUID | None = None
    audit_package_id: UUID | None = None


class LedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entry_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    side: LedgerEntrySide
    amount_minor: Minor
    currency: Currency
    line_index: int = Field(ge=1, le=1024)
    predecessor_entry_id: UUID | None = None


class LedgerJournal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    journal_id: UUID = Field(default_factory=uuid4)
    book_id: UUID
    business_event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    business_event_id: UUID
    operation: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    idempotency_key: str = Field(min_length=16, max_length=128)
    actor_identity_id: UUID
    source_system: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    traceability: LedgerTraceability
    predecessor_ledger_journal_id: UUID | None = None
    entries: tuple[LedgerEntry, ...]
    effective_at: datetime
    recorded_at: datetime
    correlation_id: UUID
    causation_id: UUID
    audit_reference: UUID

    @field_validator("effective_at", "recorded_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ledger timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_entries(self) -> "LedgerJournal":
        if len(self.entries) < 2:
            raise ValueError("A journal requires at least two entries")
        if len({entry.entry_id for entry in self.entries}) != len(self.entries):
            raise ValueError("Journal entry_id values must be unique")
        if len({entry.line_index for entry in self.entries}) != len(self.entries):
            raise ValueError("Journal line_index values must be unique")
        currencies = {entry.currency for entry in self.entries}
        if len(currencies) != 1:
            raise ValueError("A journal must use a single currency")
        totals = {
            LedgerEntrySide.DEBIT: 0,
            LedgerEntrySide.CREDIT: 0,
        }
        for entry in self.entries:
            totals[entry.side] += entry.amount_minor
        if totals[LedgerEntrySide.DEBIT] != totals[LedgerEntrySide.CREDIT]:
            raise ValueError("A journal must be balanced")
        if self.traceability.predecessor_ledger_journal_id is not None and not any(
            entry.predecessor_entry_id is not None for entry in self.entries
        ):
            raise ValueError(
                "Compensating journals must link at least one predecessor entry"
            )
        if (
            self.predecessor_ledger_journal_id is not None
            and self.traceability.predecessor_ledger_journal_id
            != self.predecessor_ledger_journal_id
        ):
            raise ValueError("Journal predecessor lineage must match traceability")
        return self


class LedgerBalance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: UUID
    currency: Currency
    debit_total_minor: int = Field(ge=0)
    credit_total_minor: int = Field(ge=0)
    net_minor: int
