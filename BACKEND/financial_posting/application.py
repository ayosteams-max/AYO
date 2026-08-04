from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.financial_posting.authorization import (
    FINANCIAL_POSTING_CREATE_PERMISSION,
    FINANCIAL_POSTING_TRACE_READ_PERMISSION,
    SUPPORT_FINANCIAL_POSTING_READ_STATUS_PERMISSION,
    is_service_identity,
)
from BACKEND.financial_posting.engine import (
    FinancialPostingConflict,
    validate_balanced_lines,
)
from BACKEND.financial_posting.models import (
    FinancialPosting,
    FinancialPostingCommand,
    FinancialPostingEntrySide,
    FinancialPostingLine,
    FinancialPostingResult,
    FinancialPostingSourceType,
)
from BACKEND.ledger.models import (
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.payment.models import PaymentAttemptState
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.tables import ledger_accounts
from BACKEND.refund.models import RefundRequestState
from BACKEND.settlement.models import SettlementBatchState
from BACKEND.wallet.application import WalletOrchestrationService
from BACKEND.wallet.models import (
    WalletAuthoritativeSourceType,
    WalletEntryType,
)


class FinancialPostingStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    posting: FinancialPosting
    lines: tuple[FinancialPostingLine, ...]


class FinancialPostingApplicationService:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition
        self._wallets = WalletOrchestrationService(composition)

    def post(
        self,
        subject: AuthorizationSubject,
        command: FinancialPostingCommand,
    ) -> FinancialPostingResult:
        self._require_permission(
            subject,
            FINANCIAL_POSTING_CREATE_PERMISSION,
            at=command.occurred_at,
        )
        if not is_service_identity(subject.identity_type):
            raise FinancialPostingConflict(
                "financial_posting_service_identity_required"
            )

        total_debit, total_credit = validate_balanced_lines(
            command.lines,
            at=command.occurred_at,
        )
        posting_candidate = uuid4()
        with self._composition.unit_of_work() as unit:
            traceability = self._validate_and_resolve_lineage(unit, command)
            canonical = unit.financial_postings.reserve_idempotency(
                actor_id=subject.identity_id,
                operation=command.operation,
                key=command.idempotency_key,
                payload={
                    "source_type": command.source_type.value,
                    "source_id": str(command.source_id),
                    "operation": command.operation,
                    "reason_code": command.reason_code,
                    "currency": command.currency,
                    "lines": "|".join(
                        f"{item.line_index}:{item.account_id}:{item.side.value}:{item.amount_minor}"
                        for item in sorted(
                            command.lines, key=lambda value: value.line_index
                        )
                    ),
                    "wallet_owner_identity_id": str(command.wallet_owner_identity_id),
                    "wallet_amount_minor": str(command.wallet_amount_minor),
                },
                response_reference=posting_candidate,
                at=command.occurred_at,
            )
            existing = unit.financial_postings.get_posting(canonical)
            if existing is not None:
                return FinancialPostingResult(
                    posting=existing,
                    lines=unit.financial_postings.list_lines(existing.posting_id),
                )

            ledger_journal = unit.ledger.post_journal(
                LedgerJournal(
                    book_id=self._book_id_from_lines(command.lines, unit),
                    business_event_type=f"financial_posting.{command.source_type.value}",
                    business_event_id=command.source_id,
                    operation=command.operation,
                    idempotency_key=command.idempotency_key,
                    actor_identity_id=subject.identity_id,
                    source_system="financial_posting_engine",
                    reason_code=command.reason_code,
                    traceability=traceability,
                    entries=tuple(
                        LedgerEntry(
                            account_id=item.account_id,
                            side=LedgerEntrySide.DEBIT
                            if item.side is FinancialPostingEntrySide.DEBIT
                            else LedgerEntrySide.CREDIT,
                            amount_minor=item.amount_minor,
                            currency=command.currency,
                            line_index=item.line_index,
                            predecessor_entry_id=self._resolve_predecessor_entry(
                                unit,
                                traceability,
                                item.account_id,
                                LedgerEntrySide.DEBIT
                                if item.side is FinancialPostingEntrySide.DEBIT
                                else LedgerEntrySide.CREDIT,
                            ),
                        )
                        for item in sorted(
                            command.lines, key=lambda value: value.line_index
                        )
                    ),
                    effective_at=command.occurred_at,
                    recorded_at=command.occurred_at,
                    correlation_id=command.correlation_id,
                    causation_id=command.causation_id,
                    audit_reference=uuid4(),
                )
            )

            wallet_entry_type = self._wallet_entry_type_for(command.source_type)
            wallet_account = self._wallets.consume_authoritative_event_with_unit(
                unit,
                subject,
                owner_identity_id=command.wallet_owner_identity_id,
                authoritative_source_type=WalletAuthoritativeSourceType.LEDGER_JOURNAL,
                authoritative_source_id=ledger_journal.journal_id,
                entry_type=wallet_entry_type,
                amount_minor=command.wallet_amount_minor,
                reason_code=f"financial_posting.wallet.{command.source_type.value}",
                idempotency_key=(
                    f"wallet:{command.operation}:{command.idempotency_key}"
                ),
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                at=command.occurred_at,
            )
            latest_wallet_lineage = unit.wallets.list_lineage(
                wallet_account.wallet_account_id
            )
            if not latest_wallet_lineage:
                raise FinancialPostingConflict(
                    "financial_posting_wallet_lineage_missing"
                )
            wallet_entry_id = latest_wallet_lineage[-1].wallet_entry_id

            posting = FinancialPosting(
                posting_id=canonical,
                source_type=command.source_type,
                source_id=command.source_id,
                operation=command.operation,
                reason_code=command.reason_code,
                currency=command.currency,
                total_debit_minor=total_debit,
                total_credit_minor=total_credit,
                actor_identity_id=subject.identity_id,
                ledger_journal_id=ledger_journal.journal_id,
                wallet_entry_id=wallet_entry_id,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                created_at=command.occurred_at,
            )
            lines = tuple(
                FinancialPostingLine(
                    posting_id=posting.posting_id,
                    line_index=item.line_index,
                    account_id=item.account_id,
                    side=item.side,
                    amount_minor=item.amount_minor,
                    currency=command.currency,
                )
                for item in sorted(command.lines, key=lambda value: value.line_index)
            )
            unit.financial_postings.create_posting(posting, lines)
            return FinancialPostingResult(posting=posting, lines=lines)

    def posting_status(
        self,
        subject: AuthorizationSubject,
        *,
        posting_id: UUID,
        at: datetime,
    ) -> FinancialPostingStatus:
        with self._composition.unit_of_work() as unit:
            posting = unit.financial_postings.get_posting(posting_id)
            if posting is None:
                raise FinancialPostingConflict("financial_posting_not_found")
            if not unit.authorization.has_permission(
                subject.identity_id,
                FINANCIAL_POSTING_TRACE_READ_PERMISSION,
                at=at,
            ) and not unit.authorization.has_permission(
                subject.identity_id,
                SUPPORT_FINANCIAL_POSTING_READ_STATUS_PERMISSION,
                at=at,
            ):
                raise FinancialPostingConflict("financial_posting_status_not_found")
            return FinancialPostingStatus(
                posting=posting,
                lines=unit.financial_postings.list_lines(posting_id),
            )

    def _validate_and_resolve_lineage(
        self,
        unit,
        command: FinancialPostingCommand,
    ) -> LedgerTraceability:
        if command.source_type is FinancialPostingSourceType.COMPLETED_PAYMENT:
            attempt = unit.payments.get_attempt(command.source_id)
            if attempt is None:
                raise FinancialPostingConflict("financial_posting_lineage_missing")
            if attempt.state is not PaymentAttemptState.CAPTURED:
                raise FinancialPostingConflict("financial_posting_invalid_lineage")
            intent = unit.payments.get_intent(attempt.payment_intent_id)
            if intent is None:
                raise FinancialPostingConflict("financial_posting_lineage_missing")
            if intent.traceability.ledger_journal_id is None:
                raise FinancialPostingConflict("financial_posting_invalid_lineage")
            return LedgerTraceability(
                ride_request_id=intent.traceability.ride_request_id,
                dispatch_handoff_id=intent.traceability.dispatch_handoff_id,
                assignment_id=intent.traceability.assignment_id,
                active_ride_id=intent.traceability.active_ride_id,
                fare_estimate_id=intent.traceability.fare_estimate_id,
                fare_calculation_id=intent.traceability.fare_calculation_id,
                predecessor_ledger_journal_id=intent.traceability.ledger_journal_id,
            )

        if command.source_type is FinancialPostingSourceType.APPROVED_REFUND:
            refund = unit.refunds.get_request(command.source_id)
            if refund is None:
                raise FinancialPostingConflict("financial_posting_lineage_missing")
            if refund.state not in {
                RefundRequestState.APPROVED,
                RefundRequestState.SCHEDULED,
                RefundRequestState.COMPLETED,
            }:
                raise FinancialPostingConflict("financial_posting_invalid_lineage")
            return LedgerTraceability(
                ride_request_id=refund.traceability.ride_request_id,
                dispatch_handoff_id=refund.traceability.dispatch_handoff_id,
                assignment_id=refund.traceability.assignment_id,
                active_ride_id=refund.traceability.active_ride_id,
                fare_estimate_id=refund.traceability.fare_estimate_id,
                fare_calculation_id=refund.traceability.fare_calculation_id,
                predecessor_ledger_journal_id=refund.traceability.ledger_journal_id,
            )

        if command.source_type is FinancialPostingSourceType.SETTLEMENT_EVENT:
            batch = unit.settlements.get_batch(command.source_id)
            if batch is None:
                raise FinancialPostingConflict("financial_posting_lineage_missing")
            if batch.state not in {
                SettlementBatchState.BALANCED,
                SettlementBatchState.READY_FOR_SETTLEMENT,
                SettlementBatchState.RESOLVED,
            }:
                raise FinancialPostingConflict("financial_posting_invalid_lineage")
            items = unit.settlements.list_items(batch.settlement_batch_id)
            if not items:
                raise FinancialPostingConflict("financial_posting_lineage_missing")
            first = items[0]
            return LedgerTraceability(
                ride_request_id=first.traceability.ride_request_id,
                dispatch_handoff_id=first.traceability.dispatch_handoff_id,
                assignment_id=first.traceability.assignment_id,
                active_ride_id=first.traceability.active_ride_id,
                fare_estimate_id=first.traceability.fare_estimate_id,
                fare_calculation_id=first.traceability.fare_calculation_id,
                predecessor_ledger_journal_id=first.traceability.ledger_journal_id,
            )

        if command.source_type is FinancialPostingSourceType.WALLET_ADJUSTMENT:
            raise FinancialPostingConflict("financial_posting_source_not_supported")

        raise FinancialPostingConflict("financial_posting_source_not_supported")

    @staticmethod
    def _book_id_from_lines(lines, unit) -> UUID:
        first = lines[0]
        row = (
            unit.connection.execute(
                select(ledger_accounts.c.book_id).where(
                    ledger_accounts.c.account_id == first.account_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise FinancialPostingConflict("financial_posting_ledger_account_not_found")
        book_id = row["book_id"]
        account_ids = [item.account_id for item in lines]
        account_count = unit.connection.execute(
            select(func.count())
            .select_from(ledger_accounts)
            .where(ledger_accounts.c.account_id.in_(account_ids))
        ).scalar_one()
        if int(account_count) != len(set(account_ids)):
            raise FinancialPostingConflict("financial_posting_ledger_account_not_found")
        mismatch = unit.connection.execute(
            select(ledger_accounts.c.account_id).where(
                ledger_accounts.c.account_id.in_(account_ids),
                ledger_accounts.c.book_id != book_id,
            )
        ).first()
        if mismatch is not None:
            raise FinancialPostingConflict("financial_posting_ledger_book_mismatch")
        return book_id

    @staticmethod
    def _wallet_entry_type_for(
        source_type: FinancialPostingSourceType,
    ) -> WalletEntryType:
        if source_type is FinancialPostingSourceType.COMPLETED_PAYMENT:
            return WalletEntryType.PENDING_CREDIT
        if source_type is FinancialPostingSourceType.APPROVED_REFUND:
            return WalletEntryType.AVAILABLE_DEBIT
        if source_type is FinancialPostingSourceType.SETTLEMENT_EVENT:
            return WalletEntryType.PENDING_RELEASE
        raise FinancialPostingConflict("financial_posting_source_not_supported")

    @staticmethod
    def _resolve_predecessor_entry(
        unit,
        traceability: LedgerTraceability,
        account_id: UUID,
        side: LedgerEntrySide,
    ) -> UUID | None:
        predecessor_journal_id = traceability.predecessor_ledger_journal_id
        if predecessor_journal_id is None:
            return None
        predecessor = unit.ledger.get_journal(predecessor_journal_id)
        if predecessor is None:
            raise FinancialPostingConflict("financial_posting_invalid_lineage")
        for entry in predecessor.entries:
            if entry.account_id == account_id and entry.side is side:
                return entry.entry_id
        raise FinancialPostingConflict("financial_posting_invalid_lineage")

    def _require_permission(
        self,
        subject: AuthorizationSubject,
        permission: str,
        *,
        at: datetime,
    ) -> None:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id,
                permission,
                at=at,
            ):
                raise FinancialPostingConflict("access_denied")
