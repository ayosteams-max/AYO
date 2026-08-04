import hashlib
import json
from datetime import datetime
from typing import Any

from BACKEND.financial_posting.models import (
    FinancialPostingEntrySide,
    FinancialPostingLineCommand,
)
from BACKEND.wallet.engine import WalletConflict


class FinancialPostingConflict(WalletConflict):
    """Financial posting conflicts reuse existing fail-closed semantics."""


def canonical_posting_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_balanced_lines(
    lines: tuple[FinancialPostingLineCommand, ...],
    *,
    at: datetime,
) -> tuple[int, int]:
    if at.tzinfo is None or at.utcoffset() is None:
        raise FinancialPostingConflict("financial_posting_timestamp_invalid")
    debit = sum(
        item.amount_minor
        for item in lines
        if item.side is FinancialPostingEntrySide.DEBIT
    )
    credit = sum(
        item.amount_minor
        for item in lines
        if item.side is FinancialPostingEntrySide.CREDIT
    )
    if debit <= 0 or credit <= 0:
        raise FinancialPostingConflict("financial_posting_amount_invalid")
    if debit != credit:
        raise FinancialPostingConflict("financial_posting_not_balanced")
    return debit, credit
