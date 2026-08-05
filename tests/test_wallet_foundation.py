from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.wallet.engine import (
    WalletConflict,
    apply_wallet_entry,
    canonical_wallet_hash,
)
from BACKEND.wallet.models import WalletEntryType

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def test_wallet_hash_deterministic_for_key_ordering() -> None:
    left = {
        "authoritative_source_id": str(uuid4()),
        "entry_type": "pending_credit",
        "amount_minor": 1200,
    }
    right = {
        "amount_minor": 1200,
        "entry_type": "pending_credit",
        "authoritative_source_id": left["authoritative_source_id"],
    }
    assert canonical_wallet_hash(left) == canonical_wallet_hash(right)


def test_wallet_entry_transitions_apply_balances() -> None:
    available, pending = apply_wallet_entry(
        available_minor=0,
        pending_minor=0,
        entry_type=WalletEntryType.PENDING_CREDIT,
        amount_minor=900,
        at=NOW,
    )
    assert available == 0
    assert pending == 900

    available, pending = apply_wallet_entry(
        available_minor=available,
        pending_minor=pending,
        entry_type=WalletEntryType.PENDING_RELEASE,
        amount_minor=400,
        at=NOW,
    )
    assert available == 400
    assert pending == 500


def test_wallet_entry_rejects_insufficient_balance() -> None:
    with pytest.raises(WalletConflict, match="wallet_available_insufficient"):
        apply_wallet_entry(
            available_minor=10,
            pending_minor=0,
            entry_type=WalletEntryType.AVAILABLE_DEBIT,
            amount_minor=11,
            at=NOW,
        )
