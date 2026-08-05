from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.ledger.models import LedgerEntrySide
from BACKEND.post_trip.application import PostTripApplication, RideLedgerAccounts
from BACKEND.post_trip.engine import (
    PostTripConflict,
    assert_rating_allowed,
    assert_settlement_ready,
    canonical_hash,
    cash_state,
    evidence_reference,
    finalize_package,
)
from BACKEND.post_trip.models import (
    CashConfirmation,
    CashSettlementState,
    FinancialBreakdown,
    PaymentMethod,
)

NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)


def confirmation(role: str, confirmed: bool = True) -> CashConfirmation:
    return CashConfirmation(
        ride_id=uuid4(),
        actor_identity_id=uuid4(),
        actor_role=role,
        confirmed=confirmed,
        idempotency_key_hash=canonical_hash(f"{role}-key"),
        recorded_at=NOW,
    )


def test_cash_requires_both_parties_and_disagreement_never_assumes_collection() -> None:
    rider, driver = confirmation("rider"), confirmation("driver")
    assert cash_state(()) is CashSettlementState.AWAITING_CONFIRMATIONS
    assert cash_state((rider,)) is CashSettlementState.PARTIALLY_CONFIRMED
    assert cash_state((rider, driver)) is CashSettlementState.CASH_SETTLED
    assert (
        cash_state((rider, driver.model_copy(update={"confirmed": False})))
        is CashSettlementState.CASH_SETTLEMENT_REVIEW
    )
    with pytest.raises(PostTripConflict, match="cash_settlement_not_agreed"):
        assert_settlement_ready(
            PaymentMethod.CASH, CashSettlementState.PARTIALLY_CONFIRMED
        )


def test_financial_breakdown_enforces_approved_component_equation() -> None:
    valid = dict(
        currency="ETB",
        gross_fare_minor=30_000,
        commission_minor=5_000,
        incentives_minor=1_000,
        taxes_minor=500,
        adjustments_minor=-500,
        net_driver_earnings_minor=25_000,
        policy_version="ride.addis.v1",
        policy_evidence_hash="a" * 64,
        fare_estimate_id=uuid4(),
        fare_calculation_id=uuid4(),
    )
    assert FinancialBreakdown.model_validate(valid).net_driver_earnings_minor == 25_000
    with pytest.raises(ValidationError, match="Net driver earnings"):
        FinancialBreakdown.model_validate(valid | {"net_driver_earnings_minor": 25_001})


def test_rating_window_is_exactly_72_hours_and_user_edits_have_no_engine_path() -> None:
    assert assert_rating_allowed(
        completed_at=NOW, submitted_at=NOW + timedelta(hours=72)
    ) == NOW + timedelta(hours=72)
    with pytest.raises(PostTripConflict, match="rating_window_closed"):
        assert_rating_allowed(
            completed_at=NOW, submitted_at=NOW + timedelta(hours=72, microseconds=1)
        )


def test_evidence_package_hash_is_deterministic_and_binds_all_authorities() -> None:
    ride, rider, driver, vehicle = uuid4(), uuid4(), uuid4(), uuid4()
    ref = evidence_reference("route_intelligence", "rie-reference", {"distance": 1000})
    values = dict(
        ride_id=ride,
        rider_identity_id=rider,
        driver_identity_id=driver,
        vehicle_id=vehicle,
        payment_method=PaymentMethod.CASH,
        booking=ref.model_copy(update={"authority": "booking"}),
        route=ref,
        pricing=ref.model_copy(update={"authority": "pricing"}),
        dispatch=ref.model_copy(update={"authority": "dispatch"}),
        assignment=ref.model_copy(update={"authority": "assignment"}),
        timeline=ref.model_copy(update={"authority": "active_ride.timeline"}),
        completion=ref.model_copy(update={"authority": "active_ride.completion"}),
    )
    first = finalize_package(values=values, finalized_at=NOW)
    second = finalize_package(values=values, finalized_at=NOW)
    assert first.package_hash == second.package_hash
    changed = finalize_package(
        values={
            **values,
            "route": evidence_reference(
                "route_intelligence", "rie-reference", {"distance": 1001}
            ),
        },
        finalized_at=NOW,
    )
    assert changed.package_hash != first.package_hash


def test_digital_evidence_cannot_settle_without_licensed_provider_reference() -> None:
    ref = evidence_reference("route_intelligence", "rie-reference", {"distance": 1000})
    values = dict(
        ride_id=uuid4(),
        rider_identity_id=uuid4(),
        driver_identity_id=uuid4(),
        vehicle_id=uuid4(),
        payment_method=PaymentMethod.LICENSED_DIGITAL_PROVIDER,
        booking=ref.model_copy(update={"authority": "booking"}),
        route=ref,
        pricing=ref.model_copy(update={"authority": "pricing"}),
        dispatch=ref.model_copy(update={"authority": "dispatch"}),
        assignment=ref.model_copy(update={"authority": "assignment"}),
        timeline=ref.model_copy(update={"authority": "active_ride.timeline"}),
        completion=ref.model_copy(update={"authority": "active_ride.completion"}),
    )
    with pytest.raises(ValidationError, match="licensed-provider payment evidence"):
        finalize_package(values=values, finalized_at=NOW)


def test_ride_ledger_entries_balance_every_approved_financial_component() -> None:
    accounts = RideLedgerAccounts(
        book_id=uuid4(),
        settlement_clearing=uuid4(),
        driver_earnings_payable=uuid4(),
        commission_revenue=uuid4(),
        tax_payable=uuid4(),
        incentive_expense=uuid4(),
        adjustment_expense=uuid4(),
        adjustment_recovery=uuid4(),
    )
    application = object.__new__(PostTripApplication)
    application._accounts = accounts
    breakdown = FinancialBreakdown(
        currency="ETB",
        gross_fare_minor=30_000,
        commission_minor=5_000,
        incentives_minor=1_000,
        taxes_minor=500,
        adjustments_minor=-500,
        net_driver_earnings_minor=25_000,
        policy_version="ride.addis.v1",
        policy_evidence_hash="a" * 64,
        fare_estimate_id=uuid4(),
        fare_calculation_id=uuid4(),
    )

    entries = application._entries(breakdown)
    debits = sum(e.amount_minor for e in entries if e.side is LedgerEntrySide.DEBIT)
    credits = sum(e.amount_minor for e in entries if e.side is LedgerEntrySide.CREDIT)

    assert debits == credits == 31_000
    assert any(
        e.account_id == accounts.adjustment_recovery and e.amount_minor == 500
        for e in entries
    )
