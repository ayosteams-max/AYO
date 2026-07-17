from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.ledger.engine import (
    LedgerConflict,
    canonical_posting_hash,
    deterministic_replay_view,
)
from BACKEND.ledger.models import LedgerBalance, LedgerBook, LedgerJournal
from BACKEND.persistence.tables import (
    fare_calculations,
    ledger_accounts,
    ledger_books,
    ledger_entries,
    ledger_events,
    ledger_idempotency,
    ledger_journals,
    ledger_outbox,
)


def _book(row: Any) -> LedgerBook:
    return LedgerBook.model_validate(dict(row))


def _journal(row: Any, entries: tuple[dict[str, Any], ...]) -> LedgerJournal:
    payload = dict(row)
    payload_entries = []
    journal_id = payload.get("journal_id")
    for entry in entries:
        entry_payload = dict(entry)
        if journal_id is not None and entry_payload.get("journal_id") != journal_id:
            raise LedgerConflict("ledger_journal_reconstruction_conflict")
        entry_payload.pop("journal_id", None)
        payload_entries.append(entry_payload)
    payload["entries"] = tuple(payload_entries)
    return LedgerJournal.model_validate(payload)


class PostgresLedgerRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_book(self, book: LedgerBook) -> LedgerBook:
        self._connection.execute(insert(ledger_books).values(**book.model_dump()))
        return book

    def get_book(self, book_id: UUID) -> LedgerBook | None:
        row = (
            self._connection.execute(
                select(ledger_books).where(ledger_books.c.book_id == book_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _book(row)

    def _ensure_traceability_source(self, journal: LedgerJournal) -> None:
        row = (
            self._connection.execute(
                select(fare_calculations.c.financial_traceability).where(
                    fare_calculations.c.calculation_id
                    == journal.traceability.fare_calculation_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LedgerConflict("ledger_traceability_conflict")
        source = row["financial_traceability"]
        checks = {
            "ride_request_id": journal.traceability.ride_request_id,
            "dispatch_handoff_id": journal.traceability.dispatch_handoff_id,
            "assignment_id": journal.traceability.assignment_id,
            "active_ride_id": journal.traceability.active_ride_id,
            "fare_estimate_id": journal.traceability.fare_estimate_id,
            "fare_calculation_id": journal.traceability.fare_calculation_id,
        }
        for key, expected in checks.items():
            if str(source.get(key)) != str(expected):
                raise LedgerConflict("ledger_traceability_conflict")

    def _ensure_accounts(self, journal: LedgerJournal) -> None:
        account_ids = {entry.account_id for entry in journal.entries}
        rows = self._connection.execute(
            select(ledger_accounts.c.account_id, ledger_accounts.c.currency).where(
                ledger_accounts.c.account_id.in_(account_ids)
            )
        ).mappings()
        available = {row["account_id"]: row["currency"] for row in rows}
        if len(available) != len(account_ids):
            raise LedgerConflict("ledger_account_not_found")
        for entry in journal.entries:
            if available[entry.account_id] != entry.currency:
                raise LedgerConflict("ledger_currency_mismatch")

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        digest = canonical_posting_hash(payload)
        row = self._connection.execute(
            pg_insert(ledger_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(ledger_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if row is not None:
            return cast(UUID, row)
        existing = (
            self._connection.execute(
                select(ledger_idempotency).where(
                    ledger_idempotency.c.actor_id == actor_id,
                    ledger_idempotency.c.operation == operation,
                    ledger_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if existing["request_hash"] != digest:
            raise LedgerConflict("idempotency_conflict")
        return cast(UUID, existing["response_reference"])

    def post_journal(self, journal: LedgerJournal) -> LedgerJournal:
        self._ensure_traceability_source(journal)
        self._ensure_accounts(journal)
        if journal.traceability.predecessor_ledger_journal_id is not None:
            predecessor = self.get_journal(
                journal.traceability.predecessor_ledger_journal_id
            )
            if predecessor is None:
                raise LedgerConflict("ledger_predecessor_not_found")
            if (
                predecessor.traceability.fare_calculation_id
                != journal.traceability.fare_calculation_id
            ):
                raise LedgerConflict("ledger_traceability_conflict")

        self._connection.execute(
            insert(ledger_journals).values(
                **journal.model_dump(exclude={"entries"}, mode="json")
            )
        )
        self._connection.execute(
            insert(ledger_entries),
            [
                {
                    **entry.model_dump(mode="json"),
                    "journal_id": journal.journal_id,
                }
                for entry in journal.entries
            ],
        )
        event_id = uuid4()
        replay = deterministic_replay_view(journal)
        self._connection.execute(
            insert(ledger_events).values(
                event_id=event_id,
                aggregate_type="ledger_journal",
                aggregate_id=journal.journal_id,
                event_type="ledger.journal_posted",
                schema_version=1,
                safe_payload={
                    "journal_id": str(journal.journal_id),
                    "book_id": str(journal.book_id),
                    "business_event_type": journal.business_event_type,
                    "business_event_id": str(journal.business_event_id),
                    "currency": journal.entries[0].currency,
                },
                replay_payload=replay,
                occurred_at=journal.recorded_at,
                correlation_id=journal.correlation_id,
                causation_id=journal.causation_id,
            )
        )
        self._connection.execute(
            insert(ledger_outbox).values(
                message_id=uuid4(),
                event_id=event_id,
                event_type="ledger.journal_posted",
                safe_payload={
                    "journal_id": str(journal.journal_id),
                    "traceability": journal.traceability.model_dump(mode="json"),
                },
                occurred_at=journal.recorded_at,
                available_at=journal.recorded_at,
            )
        )
        return journal

    def get_journal(self, journal_id: UUID) -> LedgerJournal | None:
        row = (
            self._connection.execute(
                select(ledger_journals).where(
                    ledger_journals.c.journal_id == journal_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        entry_rows = self._connection.execute(
            select(ledger_entries)
            .where(ledger_entries.c.journal_id == journal_id)
            .order_by(ledger_entries.c.line_index)
        ).mappings()
        return _journal(row, tuple(dict(item) for item in entry_rows))

    def account_balance(self, account_id: UUID, currency: str) -> LedgerBalance:
        rows = self._connection.execute(
            select(ledger_entries.c.side, ledger_entries.c.amount_minor).where(
                ledger_entries.c.account_id == account_id,
                ledger_entries.c.currency == currency,
            )
        ).mappings()
        debit_total = 0
        credit_total = 0
        for row in rows:
            if row["side"] == "debit":
                debit_total += int(row["amount_minor"])
            else:
                credit_total += int(row["amount_minor"])
        return LedgerBalance(
            account_id=account_id,
            currency=currency,
            debit_total_minor=debit_total,
            credit_total_minor=credit_total,
            net_minor=debit_total - credit_total,
        )
