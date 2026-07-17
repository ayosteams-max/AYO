from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.ledger.engine import (
    LedgerConflict,
    canonical_posting_hash,
    deterministic_replay_view,
)
from BACKEND.ledger.models import (
    LedgerEntry,
    LedgerEntrySide,
    LedgerJournal,
    LedgerTraceability,
)
from BACKEND.persistence.ledger_repository import _journal

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def traceability() -> LedgerTraceability:
    return LedgerTraceability(
        ride_request_id=uuid4(),
        dispatch_handoff_id=uuid4(),
        assignment_id=uuid4(),
        active_ride_id=uuid4(),
        fare_estimate_id=uuid4(),
        fare_calculation_id=uuid4(),
    )


def entries() -> tuple[LedgerEntry, LedgerEntry, LedgerEntry]:
    account_a = uuid4()
    account_b = uuid4()
    return (
        LedgerEntry(
            account_id=account_a,
            side=LedgerEntrySide.DEBIT,
            amount_minor=1000,
            currency="ETB",
            line_index=1,
        ),
        LedgerEntry(
            account_id=account_b,
            side=LedgerEntrySide.CREDIT,
            amount_minor=700,
            currency="ETB",
            line_index=2,
        ),
        LedgerEntry(
            account_id=account_b,
            side=LedgerEntrySide.CREDIT,
            amount_minor=300,
            currency="ETB",
            line_index=3,
        ),
    )


def test_ledger_journal_requires_balance_and_single_currency() -> None:
    with pytest.raises(ValidationError):
        LedgerJournal(
            book_id=uuid4(),
            business_event_type="pricing.final_calculated",
            business_event_id=uuid4(),
            operation="post_journal",
            idempotency_key="x" * 16,
            actor_identity_id=uuid4(),
            source_system="pricing",
            reason_code="pricing.final_charge",
            traceability=traceability(),
            entries=(
                LedgerEntry(
                    account_id=uuid4(),
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=1,
                ),
                LedgerEntry(
                    account_id=uuid4(),
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=99,
                    currency="ETB",
                    line_index=2,
                ),
            ),
            effective_at=NOW,
            recorded_at=NOW,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            audit_reference=uuid4(),
        )

    with pytest.raises(ValidationError):
        LedgerJournal(
            book_id=uuid4(),
            business_event_type="pricing.final_calculated",
            business_event_id=uuid4(),
            operation="post_journal",
            idempotency_key="y" * 16,
            actor_identity_id=uuid4(),
            source_system="pricing",
            reason_code="pricing.final_charge",
            traceability=traceability(),
            entries=(
                LedgerEntry(
                    account_id=uuid4(),
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=1,
                ),
                LedgerEntry(
                    account_id=uuid4(),
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=100,
                    currency="USD",
                    line_index=2,
                ),
            ),
            effective_at=NOW,
            recorded_at=NOW,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            audit_reference=uuid4(),
        )


def test_canonical_hash_and_replay_are_deterministic() -> None:
    item = LedgerJournal(
        book_id=uuid4(),
        business_event_type="pricing.final_calculated",
        business_event_id=uuid4(),
        operation="post_journal",
        idempotency_key="k" * 16,
        actor_identity_id=uuid4(),
        source_system="pricing",
        reason_code="pricing.final_charge",
        traceability=traceability(),
        entries=entries(),
        effective_at=NOW,
        recorded_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        audit_reference=uuid4(),
    )
    replay = deterministic_replay_view(item)
    assert replay["entries"][0]["line_index"] == 1
    digest_a = canonical_posting_hash(replay)
    digest_b = canonical_posting_hash(deterministic_replay_view(item))
    assert digest_a == digest_b


def test_ledger_journal_rejects_duplicate_entry_ids() -> None:
    duplicate_entry_id = uuid4()
    with pytest.raises(ValidationError, match="entry_id values must be unique"):
        LedgerJournal(
            book_id=uuid4(),
            business_event_type="pricing.final_calculated",
            business_event_id=uuid4(),
            operation="post_journal",
            idempotency_key="z" * 16,
            actor_identity_id=uuid4(),
            source_system="pricing",
            reason_code="pricing.final_charge",
            traceability=traceability(),
            entries=(
                LedgerEntry(
                    entry_id=duplicate_entry_id,
                    account_id=uuid4(),
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=1,
                ),
                LedgerEntry(
                    entry_id=duplicate_entry_id,
                    account_id=uuid4(),
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=2,
                ),
            ),
            effective_at=NOW,
            recorded_at=NOW,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            audit_reference=uuid4(),
        )


def test_ledger_journal_rejects_invalid_predecessor_lineage() -> None:
    predecessor_ledger_journal_id = uuid4()
    with pytest.raises(
        ValidationError, match="Journal predecessor lineage must match traceability"
    ):
        LedgerJournal(
            book_id=uuid4(),
            business_event_type="pricing.final_calculated",
            business_event_id=uuid4(),
            operation="post_journal",
            idempotency_key="p" * 16,
            actor_identity_id=uuid4(),
            source_system="pricing",
            reason_code="pricing.final_charge",
            traceability=LedgerTraceability(
                ride_request_id=uuid4(),
                dispatch_handoff_id=uuid4(),
                assignment_id=uuid4(),
                active_ride_id=uuid4(),
                fare_estimate_id=uuid4(),
                fare_calculation_id=uuid4(),
                predecessor_ledger_journal_id=predecessor_ledger_journal_id,
            ),
            predecessor_ledger_journal_id=uuid4(),
            entries=(
                LedgerEntry(
                    account_id=uuid4(),
                    side=LedgerEntrySide.DEBIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=1,
                    predecessor_entry_id=uuid4(),
                ),
                LedgerEntry(
                    account_id=uuid4(),
                    side=LedgerEntrySide.CREDIT,
                    amount_minor=100,
                    currency="ETB",
                    line_index=2,
                ),
            ),
            effective_at=NOW,
            recorded_at=NOW,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            audit_reference=uuid4(),
        )


def test_journal_reconstruction_rejects_corrupted_entry_lineage() -> None:
    journal_id = uuid4()
    row = {
        "journal_id": journal_id,
        "book_id": uuid4(),
        "business_event_type": "pricing.final_calculated",
        "business_event_id": uuid4(),
        "operation": "post_journal",
        "idempotency_key": "r" * 16,
        "actor_identity_id": uuid4(),
        "source_system": "pricing",
        "reason_code": "pricing.final_charge",
        "traceability": {
            **traceability().model_dump(mode="json"),
            "predecessor_ledger_journal_id": uuid4(),
        },
        "predecessor_ledger_journal_id": uuid4(),
        "effective_at": NOW,
        "recorded_at": NOW,
        "correlation_id": uuid4(),
        "causation_id": uuid4(),
        "audit_reference": uuid4(),
    }
    entry_a = LedgerEntry(
        account_id=uuid4(),
        side=LedgerEntrySide.DEBIT,
        amount_minor=100,
        currency="ETB",
        line_index=1,
    ).model_dump(mode="json")
    entry_b = LedgerEntry(
        account_id=uuid4(),
        side=LedgerEntrySide.CREDIT,
        amount_minor=100,
        currency="ETB",
        line_index=2,
    ).model_dump(mode="json")
    stored_entry_a = {**entry_a, "journal_id": journal_id}
    stored_entry_b = {**entry_b, "journal_id": journal_id}
    stored_entry_a_with_predecessor = {
        **stored_entry_a,
        "predecessor_entry_id": uuid4(),
    }

    with pytest.raises(LedgerConflict, match="ledger_journal_reconstruction_conflict"):
        _journal(row, ({**entry_a, "journal_id": uuid4()}, stored_entry_b))

    with pytest.raises(
        ValidationError, match="A journal requires at least two entries"
    ):
        _journal(row, (stored_entry_a,))

    with pytest.raises(ValidationError, match="Journal entry_id values must be unique"):
        _journal(row, (stored_entry_a, {**stored_entry_a, "line_index": 2}))

    with pytest.raises(
        ValidationError, match="Journal predecessor lineage must match traceability"
    ):
        _journal(row, (stored_entry_a_with_predecessor, stored_entry_b))
