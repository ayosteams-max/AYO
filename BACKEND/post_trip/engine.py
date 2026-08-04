import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from BACKEND.post_trip.models import (
    CashConfirmation,
    CashSettlementState,
    EvidenceReference,
    FinancialBreakdown,
    PaymentMethod,
    TripEvidencePackage,
)


class PostTripConflict(RuntimeError):
    pass


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def evidence_reference(
    authority: str, reference_id: UUID | str, payload: Any
) -> EvidenceReference:
    return EvidenceReference(
        authority=authority,
        reference_id=str(reference_id),
        evidence_hash=canonical_hash(payload),
    )


def finalize_package(
    *, values: dict[str, Any], finalized_at: datetime
) -> TripEvidencePackage:
    unhashed = {
        **values,
        "schema_version": "post_trip.evidence.v1",
        "finalized_at": finalized_at.isoformat(),
    }
    return TripEvidencePackage(
        **values,
        schema_version="post_trip.evidence.v1",
        package_hash=canonical_hash(unhashed),
        finalized_at=finalized_at,
    )


def cash_state(confirmations: tuple[CashConfirmation, ...]) -> CashSettlementState:
    latest = {item.actor_role: item.confirmed for item in confirmations}
    if not latest:
        return CashSettlementState.AWAITING_CONFIRMATIONS
    if set(latest) != {"rider", "driver"}:
        return CashSettlementState.PARTIALLY_CONFIRMED
    if latest["rider"] and latest["driver"]:
        return CashSettlementState.CASH_SETTLED
    return CashSettlementState.CASH_SETTLEMENT_REVIEW


def assert_rating_allowed(
    *, completed_at: datetime, submitted_at: datetime
) -> datetime:
    expires = completed_at + timedelta(hours=72)
    if submitted_at < completed_at or submitted_at > expires:
        raise PostTripConflict("rating_window_closed")
    return expires


def assert_settlement_ready(
    method: PaymentMethod, state: CashSettlementState | None
) -> None:
    if method is PaymentMethod.CASH and state is not CashSettlementState.CASH_SETTLED:
        raise PostTripConflict("cash_settlement_not_agreed")


def validate_breakdown(value: FinancialBreakdown) -> FinancialBreakdown:
    return value
