import hashlib
import json
from datetime import datetime
from typing import Any

from BACKEND.financial_control.models import FinancialHoldState
from BACKEND.financial_posting.engine import FinancialPostingConflict


class FinancialHoldConflict(FinancialPostingConflict):
    """Financial hold conflicts extend fail-closed financial semantics."""


_ALLOWED_TRANSITIONS: dict[FinancialHoldState, frozenset[FinancialHoldState]] = {
    FinancialHoldState.CREATED: frozenset(
        {
            FinancialHoldState.ACTIVE,
            FinancialHoldState.CANCELLED,
            FinancialHoldState.EXPIRED,
        }
    ),
    FinancialHoldState.ACTIVE: frozenset(
        {
            FinancialHoldState.UNDER_REVIEW,
            FinancialHoldState.RELEASED,
            FinancialHoldState.ESCALATED,
            FinancialHoldState.EXPIRED,
            FinancialHoldState.CANCELLED,
        }
    ),
    FinancialHoldState.UNDER_REVIEW: frozenset(
        {
            FinancialHoldState.ACTIVE,
            FinancialHoldState.RELEASED,
            FinancialHoldState.ESCALATED,
            FinancialHoldState.EXPIRED,
            FinancialHoldState.CANCELLED,
        }
    ),
    FinancialHoldState.ESCALATED: frozenset(
        {
            FinancialHoldState.UNDER_REVIEW,
            FinancialHoldState.RELEASED,
            FinancialHoldState.EXPIRED,
            FinancialHoldState.CANCELLED,
        }
    ),
    FinancialHoldState.RELEASED: frozenset(),
    FinancialHoldState.EXPIRED: frozenset(),
    FinancialHoldState.CANCELLED: frozenset(),
}


def canonical_hold_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ensure_transition_allowed(
    current: FinancialHoldState,
    target: FinancialHoldState,
    *,
    at: datetime,
) -> None:
    if current == target:
        return
    if at.tzinfo is None or at.utcoffset() is None:
        raise FinancialHoldConflict("financial_hold_timestamp_invalid")
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise FinancialHoldConflict("financial_hold_transition_invalid")


def hold_is_terminal(state: FinancialHoldState) -> bool:
    return state in {
        FinancialHoldState.RELEASED,
        FinancialHoldState.EXPIRED,
        FinancialHoldState.CANCELLED,
    }
