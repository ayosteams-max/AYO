from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.financial_posting.engine import (
    FinancialPostingConflict,
    canonical_posting_hash,
    validate_balanced_lines,
)
from BACKEND.financial_posting.models import (
    FinancialPostingCommand,
    FinancialPostingEntrySide,
    FinancialPostingLineCommand,
    FinancialPostingSourceType,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def test_posting_hash_deterministic_for_key_ordering() -> None:
    left = {
        "source_type": "completed_payment",
        "source_id": str(uuid4()),
        "operation": "financial.posting.create",
    }
    right = {
        "operation": "financial.posting.create",
        "source_id": left["source_id"],
        "source_type": "completed_payment",
    }
    assert canonical_posting_hash(left) == canonical_posting_hash(right)


def test_validate_balanced_lines_requires_balanced_totals() -> None:
    lines = (
        FinancialPostingLineCommand(
            line_index=1,
            account_id=uuid4(),
            side=FinancialPostingEntrySide.DEBIT,
            amount_minor=100,
        ),
        FinancialPostingLineCommand(
            line_index=2,
            account_id=uuid4(),
            side=FinancialPostingEntrySide.CREDIT,
            amount_minor=99,
        ),
    )
    with pytest.raises(
        FinancialPostingConflict, match="financial_posting_not_balanced"
    ):
        validate_balanced_lines(lines, at=NOW)


def test_validate_balanced_lines_requires_timezone_aware_timestamp() -> None:
    lines = (
        FinancialPostingLineCommand(
            line_index=1,
            account_id=uuid4(),
            side=FinancialPostingEntrySide.DEBIT,
            amount_minor=100,
        ),
        FinancialPostingLineCommand(
            line_index=2,
            account_id=uuid4(),
            side=FinancialPostingEntrySide.CREDIT,
            amount_minor=100,
        ),
    )
    with pytest.raises(
        FinancialPostingConflict,
        match="financial_posting_timestamp_invalid",
    ):
        validate_balanced_lines(lines, at=datetime(2026, 7, 17))


def test_command_rejects_non_etb_currency() -> None:
    with pytest.raises(ValidationError, match="ETB"):
        FinancialPostingCommand(
            source_type=FinancialPostingSourceType.COMPLETED_PAYMENT,
            source_id=uuid4(),
            operation="financial.posting.create",
            reason_code="financial.posting.test",
            currency="USD",
            lines=(
                FinancialPostingLineCommand(
                    line_index=1,
                    account_id=uuid4(),
                    side=FinancialPostingEntrySide.DEBIT,
                    amount_minor=100,
                ),
                FinancialPostingLineCommand(
                    line_index=2,
                    account_id=uuid4(),
                    side=FinancialPostingEntrySide.CREDIT,
                    amount_minor=100,
                ),
            ),
            wallet_owner_identity_id=uuid4(),
            wallet_amount_minor=100,
            idempotency_key="x" * 16,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            occurred_at=NOW,
        )
