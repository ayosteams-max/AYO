from datetime import UTC, datetime

import pytest

from BACKEND.financial_control.engine import (
    FinancialHoldConflict,
    canonical_hold_hash,
    ensure_transition_allowed,
)
from BACKEND.financial_control.models import FinancialHoldState
from BACKEND.financial_control.repository import FinancialHoldRepository

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def test_hold_hash_deterministic_for_key_ordering() -> None:
    left = {
        "hold_type": "rider_payment",
        "source_type": "payment_attempt",
        "source_id": "123",
    }
    right = {
        "source_id": "123",
        "source_type": "payment_attempt",
        "hold_type": "rider_payment",
    }
    assert canonical_hold_hash(left) == canonical_hold_hash(right)


def test_hold_transition_rejects_invalid_path() -> None:
    with pytest.raises(
        FinancialHoldConflict, match="financial_hold_transition_invalid"
    ):
        ensure_transition_allowed(
            FinancialHoldState.CREATED,
            FinancialHoldState.RELEASED,
            at=NOW,
        )


def test_released_hold_cannot_reactivate() -> None:
    with pytest.raises(
        FinancialHoldConflict, match="financial_hold_transition_invalid"
    ):
        ensure_transition_allowed(
            FinancialHoldState.RELEASED,
            FinancialHoldState.ACTIVE,
            at=NOW,
        )


def test_expired_hold_cannot_transition() -> None:
    with pytest.raises(
        FinancialHoldConflict, match="financial_hold_transition_invalid"
    ):
        ensure_transition_allowed(
            FinancialHoldState.EXPIRED,
            FinancialHoldState.UNDER_REVIEW,
            at=NOW,
        )


def test_repository_protocol_exposes_no_destructive_operations() -> None:
    assert not hasattr(FinancialHoldRepository, "delete_hold")
    assert not hasattr(FinancialHoldRepository, "delete_history")
