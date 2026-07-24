from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.payment.engine import (
    PaymentConflict,
    attempt_is_terminal,
    canonical_payment_hash,
    ensure_attempt_transition_allowed,
    ensure_intent_transition_allowed,
)
from BACKEND.payment.models import (
    PaymentAttemptState,
    PaymentCallbackEnvelope,
    PaymentIntent,
    PaymentIntentState,
    PaymentMethodFamily,
    PaymentTraceability,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def traceability() -> PaymentTraceability:
    return PaymentTraceability(
        ride_request_id=uuid4(),
        dispatch_handoff_id=uuid4(),
        assignment_id=uuid4(),
        active_ride_id=uuid4(),
        fare_estimate_id=uuid4(),
        fare_calculation_id=uuid4(),
    )


def test_payment_intent_enforces_payer_rider_identity_match() -> None:
    with pytest.raises(ValidationError, match="payer_identity_id must match"):
        PaymentIntent(
            ride_id=uuid4(),
            rider_identity_id=uuid4(),
            passenger_identity_id=uuid4(),
            booker_identity_id=uuid4(),
            payer_identity_id=uuid4(),
            amount_minor=1500,
            currency="ETB",
            payment_method_family=PaymentMethodFamily.CASH,
            traceability=traceability(),
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
        )


def test_payment_attempt_transition_matrix_is_fail_closed() -> None:
    ensure_attempt_transition_allowed(
        PaymentAttemptState.CREATED,
        PaymentAttemptState.AUTHORIZATION_PENDING,
        at=NOW,
    )
    ensure_attempt_transition_allowed(
        PaymentAttemptState.AUTHORIZATION_PENDING,
        PaymentAttemptState.AUTHORIZED,
        at=NOW,
    )
    ensure_attempt_transition_allowed(
        PaymentAttemptState.AUTHORIZED,
        PaymentAttemptState.CAPTURE_PENDING,
        at=NOW,
    )
    ensure_attempt_transition_allowed(
        PaymentAttemptState.CAPTURE_PENDING,
        PaymentAttemptState.CAPTURED,
        at=NOW,
    )

    with pytest.raises(PaymentConflict, match="payment_attempt_transition_invalid"):
        ensure_attempt_transition_allowed(
            PaymentAttemptState.CAPTURED,
            PaymentAttemptState.AUTHORIZED,
            at=NOW,
        )


def test_payment_hash_deterministic_for_key_ordering() -> None:
    left = {"attempt": str(uuid4()), "amount_minor": 1200, "currency": "ETB"}
    right = {"currency": "ETB", "amount_minor": 1200, "attempt": left["attempt"]}
    assert canonical_payment_hash(left) == canonical_payment_hash(right)


def test_callback_envelope_rejects_invalid_replay_window() -> None:
    with pytest.raises(ValidationError, match="replay_window_ends_at"):
        PaymentCallbackEnvelope(
            provider_code="provider.sample",
            provider_event_id="event-1",
            provider_signature_fingerprint="a" * 32,
            payload_hash="f" * 64,
            received_at=NOW,
            replay_window_ends_at=NOW,
        )


def test_payment_intent_transition_matrix_is_fail_closed() -> None:
    ensure_intent_transition_allowed(
        PaymentIntentState.CREATED,
        PaymentIntentState.CANCELLED,
        at=NOW,
    )
    with pytest.raises(PaymentConflict, match="payment_intent_transition_invalid"):
        ensure_intent_transition_allowed(
            PaymentIntentState.CANCELLED,
            PaymentIntentState.CREATED,
            at=NOW,
        )


def test_attempt_terminal_classification() -> None:
    assert attempt_is_terminal(PaymentAttemptState.CAPTURED)
    assert attempt_is_terminal(PaymentAttemptState.FAILED)
    assert not attempt_is_terminal(PaymentAttemptState.AUTHORIZATION_PENDING)
