from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.ledger.models import (
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.post_trip.engine import PostTripConflict
from BACKEND.pricing.models import FareCalculation

if TYPE_CHECKING:
    from BACKEND.persistence.composition import PostgresRepositoryComposition


class CashEvidenceState(StrEnum):
    AWAITING_CONFIRMATIONS = "awaiting_confirmations"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    COLLECTION_CORROBORATED = "collection_corroborated"
    CASH_SETTLEMENT_REVIEW = "cash_settlement_review"


class CashAccountingState(StrEnum):
    NOT_AUTHORIZED = "not_authorized"
    POLICY_VALIDATED = "policy_validated"
    ACCOUNTING_POSTED = "accounting_posted"
    ACCOUNTING_REVIEW_REQUIRED = "accounting_review_required"
    REVERSED = "reversed"


class CashReconciliationState(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    CLEARED = "cleared"
    DISPUTED = "disputed"
    WRITTEN_OFF = "written_off"


class CashAccountingModel(StrEnum):
    PRINCIPAL_GROSS = "principal_gross"
    AGENT_NET_REMITTANCE = "agent_net_remittance"


class PolicyEnvironment(StrEnum):
    NON_PRODUCTION = "non_production"
    PRODUCTION = "production"


class CashCollectionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    rider_identity_id: UUID
    driver_identity_id: UUID
    fare_calculation_id: UUID
    gross_cash_reported_minor: int = Field(ge=0, le=10_000_000_000)
    state: CashEvidenceState
    evidence_policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,62}$")
    rider_confirmation_id: UUID | None = None
    driver_confirmation_id: UUID | None = None
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_at: datetime


class CashJournalLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    side: LedgerEntrySide
    amount_minor: int = Field(ge=1, le=10_000_000_000)


class CashAccountingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    accounting_policy_id: UUID = Field(default_factory=uuid4)
    accounting_policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,62}$")
    accounting_model: CashAccountingModel
    currency: str = Field(pattern=r"^ETB$")
    effective_from: datetime
    effective_until: datetime | None = None
    environment: PolicyEnvironment
    service_type: str = Field(pattern=r"^immediate_standard$")
    payment_method: str = Field(pattern=r"^cash$")
    platform_claim_basis_points: int = Field(ge=0, le=10_000)
    driver_entitlement_basis_points: int = Field(ge=0, le=10_000)
    tax_basis_points: int = Field(ge=0, le=10_000)
    principal_receivable_account: str | None = None
    platform_claim_account: str | None = None
    driver_entitlement_account: str | None = None
    platform_revenue_account: str
    tax_payable_account: str | None = None
    reconciliation_clearing_account: str
    reconciliation_basis: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    policy_evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_reference: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def valid_model(self) -> CashAccountingPolicy:
        if (
            self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("Cash-accounting policy window is invalid")
        if self.accounting_model is CashAccountingModel.PRINCIPAL_GROSS and (
            self.principal_receivable_account is None
            or self.driver_entitlement_account is None
        ):
            raise ValueError(
                "Principal policy requires gross receivable and entitlement accounts"
            )
        if (
            self.accounting_model is CashAccountingModel.PRINCIPAL_GROSS
            and self.platform_claim_basis_points != 10_000
        ):
            raise ValueError("Principal policy must explicitly claim the gross amount")
        if (
            self.accounting_model is CashAccountingModel.AGENT_NET_REMITTANCE
            and self.platform_claim_account is None
        ):
            raise ValueError("Agent policy requires a platform-claim account")
        if self.tax_basis_points > self.platform_claim_basis_points:
            raise ValueError("Tax components cannot exceed the platform claim")
        if (
            self.accounting_model is CashAccountingModel.PRINCIPAL_GROSS
            and self.driver_entitlement_basis_points + self.tax_basis_points > 10_000
        ):
            raise ValueError("Principal policy components exceed the gross amount")
        return self


class CashAccountingInstruction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    instruction_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    fare_calculation_id: UUID
    evidence_id: UUID
    accounting_policy_id: UUID
    accounting_policy_version: str
    accounting_model: CashAccountingModel
    gross_cash_reported_minor: int = Field(ge=0)
    platform_claim_minor: int = Field(ge=0)
    driver_entitlement_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    journal_lines: tuple[CashJournalLine, ...]
    reconciliation_required: bool
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def balanced(self) -> CashAccountingInstruction:
        debit = sum(
            x.amount_minor
            for x in self.journal_lines
            if x.side is LedgerEntrySide.DEBIT
        )
        credit = sum(
            x.amount_minor
            for x in self.journal_lines
            if x.side is LedgerEntrySide.CREDIT
        )
        if not self.journal_lines or debit != credit:
            raise ValueError("Cash-accounting instruction must be balanced")
        return self


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def build_cash_accounting_instruction(
    *,
    policy: CashAccountingPolicy,
    calculation: FareCalculation,
    evidence: CashCollectionEvidence,
    at: datetime,
    production: bool,
) -> CashAccountingInstruction:
    at = at.astimezone(UTC)
    if production and policy.environment is not PolicyEnvironment.PRODUCTION:
        raise ValueError("non_production_cash_policy_rejected")
    if at < policy.effective_from or (
        policy.effective_until is not None and at >= policy.effective_until
    ):
        raise ValueError("cash_accounting_policy_inactive")
    if evidence.state is not CashEvidenceState.COLLECTION_CORROBORATED:
        raise ValueError("cash_collection_evidence_insufficient")
    if (
        evidence.ride_id != calculation.ride_id
        or evidence.fare_calculation_id != calculation.calculation_id
    ):
        raise ValueError("cash_pricing_lineage_conflict")
    if evidence.gross_cash_reported_minor != calculation.breakdown.rider_total_minor:
        raise ValueError("cash_reported_amount_conflict")
    gross_minor = evidence.gross_cash_reported_minor
    platform_claim_minor = gross_minor * policy.platform_claim_basis_points // 10_000
    driver_entitlement_minor = (
        gross_minor * policy.driver_entitlement_basis_points // 10_000
    )
    tax_minor = gross_minor * policy.tax_basis_points // 10_000
    revenue_minor = platform_claim_minor - tax_minor
    if revenue_minor < 0:
        raise ValueError("cash_tax_exceeds_platform_claim")
    if policy.accounting_model is CashAccountingModel.PRINCIPAL_GROSS:
        if platform_claim_minor != evidence.gross_cash_reported_minor:
            raise ValueError("principal_gross_claim_required")
        if (
            policy.principal_receivable_account is None
            or policy.driver_entitlement_account is None
        ):
            raise ValueError("principal_account_mapping_missing")
        lines = [
            CashJournalLine(
                account_code=policy.principal_receivable_account,
                side=LedgerEntrySide.DEBIT,
                amount_minor=platform_claim_minor,
            ),
            CashJournalLine(
                account_code=policy.driver_entitlement_account,
                side=LedgerEntrySide.CREDIT,
                amount_minor=driver_entitlement_minor,
            ),
        ]
        revenue_minor = platform_claim_minor - driver_entitlement_minor - tax_minor
    else:
        if policy.platform_claim_account is None:
            raise ValueError("agent_account_mapping_missing")
        lines = [
            CashJournalLine(
                account_code=policy.platform_claim_account,
                side=LedgerEntrySide.DEBIT,
                amount_minor=platform_claim_minor,
            )
        ]
    if revenue_minor:
        lines.append(
            CashJournalLine(
                account_code=policy.platform_revenue_account,
                side=LedgerEntrySide.CREDIT,
                amount_minor=revenue_minor,
            )
        )
    if tax_minor:
        if policy.tax_payable_account is None:
            raise ValueError("cash_tax_account_required")
        lines.append(
            CashJournalLine(
                account_code=policy.tax_payable_account,
                side=LedgerEntrySide.CREDIT,
                amount_minor=tax_minor,
            )
        )
    payload = {
        "ride_id": calculation.ride_id,
        "calculation_id": calculation.calculation_id,
        "evidence_hash": evidence.evidence_hash,
        "policy_id": policy.accounting_policy_id,
        "policy_version": policy.accounting_policy_version,
        "platform_claim_minor": platform_claim_minor,
        "driver_entitlement_minor": driver_entitlement_minor,
        "tax_minor": tax_minor,
    }
    return CashAccountingInstruction(
        ride_id=calculation.ride_id,
        fare_calculation_id=calculation.calculation_id,
        evidence_id=evidence.evidence_id,
        accounting_policy_id=policy.accounting_policy_id,
        accounting_policy_version=policy.accounting_policy_version,
        accounting_model=policy.accounting_model,
        gross_cash_reported_minor=evidence.gross_cash_reported_minor,
        platform_claim_minor=platform_claim_minor,
        driver_entitlement_minor=driver_entitlement_minor,
        tax_minor=tax_minor,
        journal_lines=tuple(lines),
        reconciliation_required=platform_claim_minor > 0,
        input_hash=_hash(payload),
        policy_hash=policy.policy_evidence_hash,
    )


class CashAccountingRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_id: UUID
    evidence_id: UUID
    instruction_id: UUID
    accounting_policy_id: UUID
    accounting_policy_version: str
    platform_claim_minor: int = Field(ge=0)
    driver_entitlement_minor: int = Field(ge=0)
    state: CashAccountingState
    ledger_journal_id: UUID | None = None
    reconciliation_state: CashReconciliationState
    clearing_journal_id: UUID | None = None
    reconciliation_evidence_hash: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    version: int = Field(ge=1)


class CashReconciliationEvidence(BaseModel):
    """Immutable synthetic/operational evidence authorizing one obligation clear."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reconciliation_evidence_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    accounting_instruction_id: UUID
    accounting_policy_id: UUID
    accounting_policy_version: str
    original_accounting_journal_id: UUID
    platform_claim_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^ETB$")
    evidence_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    source_classification: str = Field(pattern=r"^(synthetic|approved_operational)$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorized_actor_id: UUID
    occurred_at: datetime
    correlation_id: UUID
    causation_id: UUID

    @model_validator(mode="after")
    def hash_binds_authority(self) -> CashReconciliationEvidence:
        payload = self.model_dump(exclude={"evidence_hash"}, mode="json")
        if _hash(payload) != self.evidence_hash:
            raise ValueError("Reconciliation evidence hash does not bind its authority")
        return self


def build_cash_reconciliation_evidence(
    *,
    reconciliation_evidence_id: UUID,
    ride_id: UUID,
    accounting_instruction_id: UUID,
    accounting_policy_id: UUID,
    accounting_policy_version: str,
    original_accounting_journal_id: UUID,
    platform_claim_minor: int,
    currency: str,
    evidence_type: str,
    source_classification: str,
    authorized_actor_id: UUID,
    occurred_at: datetime,
    correlation_id: UUID,
    causation_id: UUID,
) -> CashReconciliationEvidence:
    values = {
        "reconciliation_evidence_id": reconciliation_evidence_id,
        "ride_id": ride_id,
        "accounting_instruction_id": accounting_instruction_id,
        "accounting_policy_id": accounting_policy_id,
        "accounting_policy_version": accounting_policy_version,
        "original_accounting_journal_id": original_accounting_journal_id,
        "platform_claim_minor": platform_claim_minor,
        "currency": currency,
        "evidence_type": evidence_type,
        "source_classification": source_classification,
        "authorized_actor_id": authorized_actor_id,
        "occurred_at": occurred_at,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
    }
    candidate = CashReconciliationEvidence.model_construct(
        reconciliation_evidence_id=reconciliation_evidence_id,
        ride_id=ride_id,
        accounting_instruction_id=accounting_instruction_id,
        accounting_policy_id=accounting_policy_id,
        accounting_policy_version=accounting_policy_version,
        original_accounting_journal_id=original_accounting_journal_id,
        platform_claim_minor=platform_claim_minor,
        currency=currency,
        evidence_type=evidence_type,
        source_classification=source_classification,
        evidence_hash="0" * 64,
        authorized_actor_id=authorized_actor_id,
        occurred_at=occurred_at,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return CashReconciliationEvidence.model_validate(
        {
            **values,
            "evidence_hash": _hash(
                candidate.model_dump(exclude={"evidence_hash"}, mode="json")
            ),
        }
    )


class CashAccountingLedgerApplication:
    """Posts only a validated policy instruction; it never selects a model."""

    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        book_id: UUID,
        account_ids: dict[str, UUID],
        production: bool,
    ) -> None:
        self._composition = composition
        self._book_id = book_id
        self._account_ids = dict(account_ids)
        self._production = production

    def post(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        fare_calculation_id: UUID,
        evidence_id: UUID,
        accounting_policy_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> CashAccountingRecord:
        if subject.identity_type is not IdentityType.SERVICE:
            raise PostTripConflict("cash_accounting_access_denied")
        with self._composition.unit_of_work() as unit:
            calculation = unit.pricing.get_calculation(fare_calculation_id)
            evidence = unit.post_trip.cash_collection_evidence(ride_id)
            policy = unit.post_trip.cash_accounting_policy(accounting_policy_id)
            if (
                calculation is None
                or evidence is None
                or policy is None
                or calculation.ride_id != ride_id
                or evidence.evidence_id != evidence_id
            ):
                raise PostTripConflict("cash_accounting_authority_missing")
            try:
                derived = build_cash_accounting_instruction(
                    policy=policy,
                    calculation=calculation,
                    evidence=evidence,
                    at=at,
                    production=self._production,
                )
            except ValueError as error:
                raise PostTripConflict("cash_accounting_policy_rejected") from error
            instruction = derived.model_copy(
                update={
                    "instruction_id": uuid5(
                        NAMESPACE_URL,
                        f"ayo:cash-accounting:{ride_id}:{fare_calculation_id}:"
                        f"{evidence_id}:{accounting_policy_id}",
                    )
                }
            )
            existing = unit.post_trip.cash_accounting_record(ride_id)
            if existing is not None:
                if existing.instruction_id != instruction.instruction_id:
                    raise PostTripConflict("cash_accounting_record_conflict")
                return existing
            try:
                entries = tuple(
                    LedgerEntry(
                        account_id=self._account_ids[line.account_code],
                        side=line.side,
                        amount_minor=line.amount_minor,
                        currency="ETB",
                        line_index=index,
                    )
                    for index, line in enumerate(instruction.journal_lines, start=1)
                )
            except KeyError as error:
                raise PostTripConflict("cash_account_mapping_missing") from error
            trace = calculation.financial_traceability
            if (
                trace.dispatch_handoff_id is None
                or trace.assignment_id is None
                or trace.active_ride_id is None
                or trace.fare_calculation_id is None
            ):
                raise PostTripConflict("cash_accounting_lineage_missing")
            journal_candidate = LedgerJournal(
                journal_id=uuid5(
                    NAMESPACE_URL,
                    f"ayo:cash-accounting-journal:{instruction.instruction_id}",
                ),
                book_id=self._book_id,
                business_event_type="ride.cash_accounting",
                business_event_id=instruction.instruction_id,
                operation="ride.cash_accounting.post",
                idempotency_key=idempotency_key,
                actor_identity_id=subject.identity_id,
                source_system="post_trip",
                reason_code="cash.policy_instruction.validated",
                traceability=LedgerTraceability(
                    ride_request_id=trace.ride_request_id,
                    dispatch_handoff_id=trace.dispatch_handoff_id,
                    assignment_id=trace.assignment_id,
                    active_ride_id=trace.active_ride_id,
                    fare_estimate_id=trace.fare_estimate_id,
                    fare_calculation_id=trace.fare_calculation_id,
                    audit_package_id=evidence.evidence_id,
                ),
                entries=entries,
                effective_at=at,
                recorded_at=at,
                correlation_id=correlation_id,
                causation_id=instruction.instruction_id,
                audit_reference=uuid4(),
            )
            canonical_journal_id = unit.ledger.reserve_idempotency(
                actor_id=subject.identity_id,
                operation=journal_candidate.operation,
                key=idempotency_key,
                payload=journal_candidate.model_dump(mode="json"),
                response_reference=journal_candidate.journal_id,
                at=at,
            )
            journal = unit.ledger.get_journal(canonical_journal_id)
            if journal is None:
                if canonical_journal_id != journal_candidate.journal_id:
                    raise PostTripConflict("cash_accounting_idempotency_corrupt")
                journal = unit.ledger.post_journal(journal_candidate)
            elif journal != journal_candidate:
                raise PostTripConflict("cash_accounting_idempotency_conflict")
            return unit.post_trip.add_cash_accounting_record(
                CashAccountingRecord(
                    ride_id=instruction.ride_id,
                    evidence_id=instruction.evidence_id,
                    instruction_id=instruction.instruction_id,
                    accounting_policy_id=instruction.accounting_policy_id,
                    accounting_policy_version=instruction.accounting_policy_version,
                    platform_claim_minor=instruction.platform_claim_minor,
                    driver_entitlement_minor=instruction.driver_entitlement_minor,
                    state=CashAccountingState.ACCOUNTING_POSTED,
                    ledger_journal_id=journal.journal_id,
                    reconciliation_state=(
                        CashReconciliationState.PENDING
                        if instruction.reconciliation_required
                        else CashReconciliationState.NOT_APPLICABLE
                    ),
                    version=1,
                )
            )


class CashReconciliationApplication:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        book_id: UUID,
        account_ids: dict[str, UUID],
        production: bool,
    ) -> None:
        self._composition = composition
        self._book_id = book_id
        self._account_ids = dict(account_ids)
        self._production = production

    def clear(
        self,
        subject: AuthorizationSubject,
        *,
        evidence: CashReconciliationEvidence,
        idempotency_key: str,
        expected_version: int,
    ) -> CashAccountingRecord:
        if subject.identity_type not in {IdentityType.SERVICE, IdentityType.STAFF}:
            raise PostTripConflict("cash_reconciliation_access_denied")
        try:
            evidence = CashReconciliationEvidence.model_validate(evidence.model_dump())
        except ValidationError as error:
            raise PostTripConflict("cash_reconciliation_evidence_invalid") from error
        if (
            self._production
            and evidence.source_classification != "approved_operational"
        ):
            raise PostTripConflict("cash_reconciliation_evidence_invalid")
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id,
                "cash.reconciliation.execute",
                at=evidence.occurred_at,
            ):
                raise PostTripConflict("cash_reconciliation_access_denied")
            item = unit.post_trip.cash_accounting_record(evidence.ride_id)
            policy = (
                None
                if item is None
                else unit.post_trip.cash_accounting_policy(item.accounting_policy_id)
            )
            original = (
                None
                if item is None or item.ledger_journal_id is None
                else unit.ledger.get_journal(item.ledger_journal_id)
            )
            if item is None or policy is None or original is None:
                raise PostTripConflict("cash_reconciliation_authority_missing")
            if item.version != expected_version:
                raise PostTripConflict("stale_cash_accounting_record")
            if (
                evidence.authorized_actor_id != subject.identity_id
                or evidence.accounting_instruction_id != item.instruction_id
                or evidence.accounting_policy_id != item.accounting_policy_id
                or evidence.accounting_policy_version != item.accounting_policy_version
                or evidence.original_accounting_journal_id != item.ledger_journal_id
                or evidence.platform_claim_minor != item.platform_claim_minor
                or evidence.currency != "ETB"
                or original.business_event_type != "ride.cash_accounting"
                or original.business_event_id != item.instruction_id
                or original.operation != "ride.cash_accounting.post"
                or original.traceability.active_ride_id != item.ride_id
            ):
                raise PostTripConflict("cash_reconciliation_authority_missing")
            if item.reconciliation_state is CashReconciliationState.CLEARED:
                if item.reconciliation_evidence_hash != evidence.evidence_hash:
                    raise PostTripConflict("cash_reconciliation_conflict")
                return item
            stored_evidence = unit.post_trip.add_cash_reconciliation_evidence(evidence)
            receivable_code = (
                policy.principal_receivable_account
                if policy.accounting_model is CashAccountingModel.PRINCIPAL_GROSS
                else policy.platform_claim_account
            )
            if receivable_code is None:
                raise PostTripConflict("cash_reconciliation_account_mapping_missing")
            try:
                receivable_id = self._account_ids[receivable_code]
                clearing_id = self._account_ids[policy.reconciliation_clearing_account]
            except KeyError as error:
                raise PostTripConflict(
                    "cash_reconciliation_account_mapping_missing"
                ) from error
            predecessor_entry = next(
                (
                    entry
                    for entry in original.entries
                    if entry.account_id == receivable_id
                    and entry.side is LedgerEntrySide.DEBIT
                    and entry.amount_minor == item.platform_claim_minor
                ),
                None,
            )
            if predecessor_entry is None:
                raise PostTripConflict("cash_reconciliation_authority_missing")
            journal_candidate = LedgerJournal(
                journal_id=uuid5(
                    NAMESPACE_URL,
                    "ayo:cash-reconciliation-journal:"
                    f"{stored_evidence.reconciliation_evidence_id}",
                ),
                book_id=self._book_id,
                business_event_type="ride.cash_reconciliation",
                business_event_id=stored_evidence.reconciliation_evidence_id,
                operation="ride.cash_reconciliation.clear",
                idempotency_key=idempotency_key,
                actor_identity_id=subject.identity_id,
                source_system="post_trip",
                reason_code="cash.remittance_evidence.authorized",
                traceability=original.traceability.model_copy(
                    update={"predecessor_ledger_journal_id": original.journal_id}
                ),
                predecessor_ledger_journal_id=original.journal_id,
                entries=(
                    LedgerEntry(
                        account_id=clearing_id,
                        side=LedgerEntrySide.DEBIT,
                        amount_minor=item.platform_claim_minor,
                        currency=evidence.currency,
                        line_index=1,
                    ),
                    LedgerEntry(
                        account_id=receivable_id,
                        side=LedgerEntrySide.CREDIT,
                        amount_minor=item.platform_claim_minor,
                        currency=evidence.currency,
                        line_index=2,
                        predecessor_entry_id=predecessor_entry.entry_id,
                    ),
                ),
                effective_at=evidence.occurred_at,
                recorded_at=evidence.occurred_at,
                correlation_id=evidence.correlation_id,
                causation_id=evidence.causation_id,
                audit_reference=evidence.reconciliation_evidence_id,
            )
            canonical_journal_id = unit.ledger.reserve_idempotency(
                actor_id=subject.identity_id,
                operation=journal_candidate.operation,
                key=idempotency_key,
                payload=journal_candidate.model_dump(mode="json"),
                response_reference=journal_candidate.journal_id,
                at=evidence.occurred_at,
            )
            journal = unit.ledger.get_journal(canonical_journal_id)
            if journal is None:
                if canonical_journal_id != journal_candidate.journal_id:
                    raise PostTripConflict("cash_reconciliation_idempotency_corrupt")
                journal = unit.ledger.post_journal(journal_candidate)
            elif journal != journal_candidate:
                raise PostTripConflict("cash_reconciliation_idempotency_conflict")
            changed = item.model_copy(
                update={
                    "reconciliation_state": CashReconciliationState.CLEARED,
                    "clearing_journal_id": journal.journal_id,
                    "reconciliation_evidence_hash": evidence.evidence_hash,
                }
            )
            return unit.post_trip.update_cash_accounting_record(
                changed, expected_version=expected_version
            )
