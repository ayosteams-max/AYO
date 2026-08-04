import hashlib
import json
from datetime import datetime
from typing import Any

from BACKEND.payment.models import PaymentAttemptState, PaymentIntentState
from BACKEND.pricing.engine import PricingConflict


class PaymentConflict(PricingConflict):
    """Payment foundation conflicts reusing existing conflict semantics."""


_ALLOWED_ATTEMPT_TRANSITIONS: dict[
    PaymentAttemptState, frozenset[PaymentAttemptState]
] = {
    PaymentAttemptState.CREATED: frozenset(
        {
            PaymentAttemptState.AUTHORIZATION_PENDING,
            PaymentAttemptState.CANCELLED,
            PaymentAttemptState.EXPIRED,
            PaymentAttemptState.FAILED,
            PaymentAttemptState.OUTCOME_UNKNOWN,
        }
    ),
    PaymentAttemptState.AUTHORIZATION_PENDING: frozenset(
        {
            PaymentAttemptState.AUTHORIZED,
            PaymentAttemptState.FAILED,
            PaymentAttemptState.CANCELLED,
            PaymentAttemptState.EXPIRED,
            PaymentAttemptState.OUTCOME_UNKNOWN,
        }
    ),
    PaymentAttemptState.AUTHORIZED: frozenset(
        {
            PaymentAttemptState.CAPTURE_PENDING,
            PaymentAttemptState.CANCELLED,
            PaymentAttemptState.FAILED,
            PaymentAttemptState.OUTCOME_UNKNOWN,
        }
    ),
    PaymentAttemptState.CAPTURE_PENDING: frozenset(
        {
            PaymentAttemptState.CAPTURED,
            PaymentAttemptState.FAILED,
            PaymentAttemptState.OUTCOME_UNKNOWN,
        }
    ),
    PaymentAttemptState.OUTCOME_UNKNOWN: frozenset(
        {
            PaymentAttemptState.AUTHORIZED,
            PaymentAttemptState.CAPTURE_PENDING,
            PaymentAttemptState.CAPTURED,
            PaymentAttemptState.FAILED,
            PaymentAttemptState.CANCELLED,
            PaymentAttemptState.EXPIRED,
        }
    ),
    PaymentAttemptState.CAPTURED: frozenset(),
    PaymentAttemptState.FAILED: frozenset(),
    PaymentAttemptState.CANCELLED: frozenset(),
    PaymentAttemptState.EXPIRED: frozenset(),
}

_ALLOWED_INTENT_TRANSITIONS: dict[PaymentIntentState, frozenset[PaymentIntentState]] = {
    PaymentIntentState.CREATED: frozenset(
        {PaymentIntentState.CANCELLED, PaymentIntentState.EXPIRED}
    ),
    PaymentIntentState.CANCELLED: frozenset(),
    PaymentIntentState.EXPIRED: frozenset(),
}


def canonical_payment_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ensure_attempt_transition_allowed(
    current: PaymentAttemptState,
    target: PaymentAttemptState,
    *,
    at: datetime,
) -> None:
    if target == current:
        return
    if target not in _ALLOWED_ATTEMPT_TRANSITIONS[current]:
        raise PaymentConflict("payment_attempt_transition_invalid")
    if at.tzinfo is None or at.utcoffset() is None:
        raise PaymentConflict("payment_timestamp_invalid")


def ensure_intent_transition_allowed(
    current: PaymentIntentState,
    target: PaymentIntentState,
    *,
    at: datetime,
) -> None:
    if target == current:
        return
    if target not in _ALLOWED_INTENT_TRANSITIONS[current]:
        raise PaymentConflict("payment_intent_transition_invalid")
    if at.tzinfo is None or at.utcoffset() is None:
        raise PaymentConflict("payment_timestamp_invalid")


def attempt_is_terminal(value: PaymentAttemptState) -> bool:
    return value in {
        PaymentAttemptState.CAPTURED,
        PaymentAttemptState.FAILED,
        PaymentAttemptState.CANCELLED,
        PaymentAttemptState.EXPIRED,
    }
