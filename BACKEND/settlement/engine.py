import hashlib
import json
from datetime import datetime
from typing import Any

from BACKEND.payment.engine import PaymentConflict
from BACKEND.settlement.models import SettlementBatchState


class SettlementConflict(PaymentConflict):
    """Settlement foundation conflicts reuse existing fail-closed semantics."""


_ALLOWED_BATCH_TRANSITIONS: dict[
    SettlementBatchState, frozenset[SettlementBatchState]
] = {
    SettlementBatchState.CREATED: frozenset(
        {
            SettlementBatchState.COLLECTING,
            SettlementBatchState.RECONCILING,
        }
    ),
    SettlementBatchState.COLLECTING: frozenset(
        {
            SettlementBatchState.RECONCILING,
        }
    ),
    SettlementBatchState.RECONCILING: frozenset(
        {
            SettlementBatchState.BALANCED,
            SettlementBatchState.EXCEPTION,
        }
    ),
    SettlementBatchState.BALANCED: frozenset(
        {
            SettlementBatchState.READY_FOR_SETTLEMENT,
        }
    ),
    SettlementBatchState.EXCEPTION: frozenset(
        {
            SettlementBatchState.MANUAL_REVIEW,
        }
    ),
    SettlementBatchState.MANUAL_REVIEW: frozenset(
        {
            SettlementBatchState.RESOLVED,
        }
    ),
    SettlementBatchState.RESOLVED: frozenset(),
    SettlementBatchState.READY_FOR_SETTLEMENT: frozenset(),
}


def canonical_settlement_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ensure_batch_transition_allowed(
    current: SettlementBatchState,
    target: SettlementBatchState,
    *,
    at: datetime,
) -> None:
    if current == target:
        return
    if at.tzinfo is None or at.utcoffset() is None:
        raise SettlementConflict("settlement_timestamp_invalid")
    if target not in _ALLOWED_BATCH_TRANSITIONS[current]:
        raise SettlementConflict("settlement_transition_invalid")


def batch_is_terminal(state: SettlementBatchState) -> bool:
    return state in {
        SettlementBatchState.READY_FOR_SETTLEMENT,
        SettlementBatchState.RESOLVED,
    }
