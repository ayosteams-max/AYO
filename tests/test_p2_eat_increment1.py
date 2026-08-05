from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.eat_availability.engine import availability_outcome, canonical_hash
from BACKEND.eat_availability.models import (
    EatAvailabilityOutcome,
    EatAvailabilityPolicy,
    EatAvailabilityState,
)
from BACKEND.ordering.models import BasketLine

NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def policy(
    *,
    state: EatAvailabilityState = EatAvailabilityState.AVAILABLE,
    effective_from: datetime = NOW - timedelta(hours=1),
    effective_until: datetime | None = NOW + timedelta(hours=1),
) -> EatAvailabilityPolicy:
    return EatAvailabilityPolicy(
        merchant_id=uuid4(),
        area_reference="area:addis:opaque",
        coverage_reference="coverage:p2:opaque",
        state=state,
        reason_code="configured",
        effective_from=effective_from,
        effective_until=effective_until,
        created_by_identity_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("state", "merchant_open", "items_available", "expected"),
    [
        (
            EatAvailabilityState.AVAILABLE,
            True,
            True,
            EatAvailabilityOutcome.AVAILABLE,
        ),
        (
            EatAvailabilityState.AVAILABLE,
            False,
            True,
            EatAvailabilityOutcome.MERCHANT_CLOSED,
        ),
        (
            EatAvailabilityState.AVAILABLE,
            True,
            False,
            EatAvailabilityOutcome.PRODUCT_UNAVAILABLE,
        ),
        (
            EatAvailabilityState.TEMPORARILY_UNAVAILABLE,
            True,
            True,
            EatAvailabilityOutcome.TEMPORARILY_UNAVAILABLE,
        ),
        (
            EatAvailabilityState.UNAVAILABLE,
            True,
            True,
            EatAvailabilityOutcome.UNAVAILABLE,
        ),
    ],
)
def test_availability_is_deterministic_and_fail_closed(
    state: EatAvailabilityState,
    merchant_open: bool,
    items_available: bool,
    expected: EatAvailabilityOutcome,
) -> None:
    outcome, _ = availability_outcome(
        policy(state=state),
        merchant_open=merchant_open,
        items_available=items_available,
        at=NOW,
    )
    assert outcome is expected


def test_missing_or_expired_policy_is_unknown_not_available() -> None:
    missing, _ = availability_outcome(
        None, merchant_open=True, items_available=True, at=NOW
    )
    expired, _ = availability_outcome(
        policy(effective_until=NOW),
        merchant_open=True,
        items_available=True,
        at=NOW,
    )
    assert missing is EatAvailabilityOutcome.UNKNOWN_OR_STALE
    assert expired is EatAvailabilityOutcome.UNKNOWN_OR_STALE


def test_invalid_effective_window_is_rejected() -> None:
    with pytest.raises(ValidationError, match="effective_until"):
        policy(effective_from=NOW, effective_until=NOW)


def test_modifier_metadata_is_bounded_and_canonical() -> None:
    line = BasketLine(
        item_id=uuid4(),
        quantity=1,
        observed_version=1,
        modifier_selections=(" Milk.Oat ", "NO_SUGAR"),
        customer_instructions="  Ring once  ",
    )
    assert line.modifier_selections == ("milk.oat", "no_sugar")
    assert line.customer_instructions == "Ring once"

    with pytest.raises(ValidationError):
        BasketLine(
            item_id=uuid4(),
            quantity=1,
            observed_version=1,
            modifier_selections=("valid", "valid"),
        )


def test_evidence_hash_is_canonical() -> None:
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
