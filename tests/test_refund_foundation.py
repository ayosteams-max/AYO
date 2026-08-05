from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.refund.engine import (
    RefundConflict,
    canonical_refund_hash,
    ensure_request_transition_allowed,
    request_is_terminal,
)
from BACKEND.refund.models import RefundRequestState

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def test_refund_request_transition_matrix_is_fail_closed() -> None:
    ensure_request_transition_allowed(
        RefundRequestState.REQUESTED,
        RefundRequestState.UNDER_REVIEW,
        at=NOW,
    )
    ensure_request_transition_allowed(
        RefundRequestState.UNDER_REVIEW,
        RefundRequestState.APPROVED,
        at=NOW,
    )
    ensure_request_transition_allowed(
        RefundRequestState.APPROVED,
        RefundRequestState.SCHEDULED,
        at=NOW,
    )
    ensure_request_transition_allowed(
        RefundRequestState.SCHEDULED,
        RefundRequestState.COMPLETED,
        at=NOW,
    )

    with pytest.raises(RefundConflict, match="refund_transition_invalid"):
        ensure_request_transition_allowed(
            RefundRequestState.COMPLETED,
            RefundRequestState.UNDER_REVIEW,
            at=NOW,
        )


def test_refund_rejection_is_terminal() -> None:
    assert request_is_terminal(RefundRequestState.REJECTED)
    assert request_is_terminal(RefundRequestState.COMPLETED)
    assert not request_is_terminal(RefundRequestState.UNDER_REVIEW)


def test_refund_hash_deterministic_for_key_ordering() -> None:
    left = {"refund_request_id": str(uuid4()), "amount_minor": 900, "currency": "ETB"}
    right = {
        "currency": "ETB",
        "amount_minor": 900,
        "refund_request_id": left["refund_request_id"],
    }
    assert canonical_refund_hash(left) == canonical_refund_hash(right)
