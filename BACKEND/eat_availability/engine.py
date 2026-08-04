import hashlib
import json
from datetime import datetime

from BACKEND.eat_availability.models import (
    EatAvailabilityOutcome,
    EatAvailabilityPolicy,
    EatAvailabilityState,
)


class EatAvailabilityConflict(ValueError):
    pass


def availability_outcome(
    policy: EatAvailabilityPolicy | None,
    *,
    merchant_open: bool,
    items_available: bool,
    at: datetime,
) -> tuple[EatAvailabilityOutcome, str]:
    if policy is None:
        return EatAvailabilityOutcome.UNKNOWN_OR_STALE, "policy_missing"
    if at < policy.effective_from or (
        policy.effective_until is not None and at >= policy.effective_until
    ):
        return EatAvailabilityOutcome.UNKNOWN_OR_STALE, "policy_not_effective"
    if policy.state is EatAvailabilityState.TEMPORARILY_UNAVAILABLE:
        return EatAvailabilityOutcome.TEMPORARILY_UNAVAILABLE, policy.reason_code
    if policy.state is EatAvailabilityState.UNAVAILABLE:
        return EatAvailabilityOutcome.UNAVAILABLE, policy.reason_code
    if not merchant_open:
        return EatAvailabilityOutcome.MERCHANT_CLOSED, "merchant_closed"
    if not items_available:
        return EatAvailabilityOutcome.PRODUCT_UNAVAILABLE, "product_unavailable"
    return EatAvailabilityOutcome.AVAILABLE, "available"


def canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
