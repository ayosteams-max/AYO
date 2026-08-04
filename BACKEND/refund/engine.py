import hashlib
import json
from datetime import datetime
from typing import Any

from BACKEND.payment.engine import PaymentConflict
from BACKEND.refund.models import RefundRequestState


class RefundConflict(PaymentConflict):
    """Refund foundation conflicts reuse existing fail-closed semantics."""


_ALLOWED_REQUEST_TRANSITIONS: dict[
    RefundRequestState, frozenset[RefundRequestState]
] = {
    RefundRequestState.REQUESTED: frozenset(
        {
            RefundRequestState.UNDER_REVIEW,
            RefundRequestState.REJECTED,
        }
    ),
    RefundRequestState.UNDER_REVIEW: frozenset(
        {
            RefundRequestState.APPROVED,
        }
    ),
    RefundRequestState.APPROVED: frozenset(
        {
            RefundRequestState.SCHEDULED,
        }
    ),
    RefundRequestState.SCHEDULED: frozenset(
        {
            RefundRequestState.COMPLETED,
        }
    ),
    RefundRequestState.COMPLETED: frozenset(),
    RefundRequestState.REJECTED: frozenset(),
}


def canonical_refund_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ensure_request_transition_allowed(
    current: RefundRequestState,
    target: RefundRequestState,
    *,
    at: datetime,
) -> None:
    if current == target:
        return
    if at.tzinfo is None or at.utcoffset() is None:
        raise RefundConflict("refund_timestamp_invalid")
    if target not in _ALLOWED_REQUEST_TRANSITIONS[current]:
        raise RefundConflict("refund_transition_invalid")


def request_is_terminal(state: RefundRequestState) -> bool:
    return state in {
        RefundRequestState.COMPLETED,
        RefundRequestState.REJECTED,
    }
