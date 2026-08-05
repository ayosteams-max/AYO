from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.settlement.engine import (
    SettlementConflict,
    batch_is_terminal,
    canonical_settlement_hash,
    ensure_batch_transition_allowed,
)
from BACKEND.settlement.models import SettlementBatchState

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def test_settlement_batch_transition_matrix_is_fail_closed() -> None:
    ensure_batch_transition_allowed(
        SettlementBatchState.CREATED,
        SettlementBatchState.COLLECTING,
        at=NOW,
    )
    ensure_batch_transition_allowed(
        SettlementBatchState.COLLECTING,
        SettlementBatchState.RECONCILING,
        at=NOW,
    )
    ensure_batch_transition_allowed(
        SettlementBatchState.RECONCILING,
        SettlementBatchState.BALANCED,
        at=NOW,
    )
    ensure_batch_transition_allowed(
        SettlementBatchState.BALANCED,
        SettlementBatchState.READY_FOR_SETTLEMENT,
        at=NOW,
    )

    with pytest.raises(SettlementConflict, match="settlement_transition_invalid"):
        ensure_batch_transition_allowed(
            SettlementBatchState.READY_FOR_SETTLEMENT,
            SettlementBatchState.BALANCED,
            at=NOW,
        )


def test_settlement_hash_deterministic_for_key_ordering() -> None:
    left = {
        "settlement_batch_id": str(uuid4()),
        "amount_minor": 1100,
        "currency": "ETB",
    }
    right = {
        "currency": "ETB",
        "amount_minor": 1100,
        "settlement_batch_id": left["settlement_batch_id"],
    }
    assert canonical_settlement_hash(left) == canonical_settlement_hash(right)


def test_settlement_terminal_classification() -> None:
    assert batch_is_terminal(SettlementBatchState.READY_FOR_SETTLEMENT)
    assert batch_is_terminal(SettlementBatchState.RESOLVED)
    assert not batch_is_terminal(SettlementBatchState.RECONCILING)
