from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.dispatch.handoff import (
    EligibleDriverInput,
    decision_reason_codes,
    rank_candidates,
)

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def candidate(eta: int, **changes) -> EligibleDriverInput:
    vehicle = uuid4()
    values = dict(
        driver_id=uuid4(),
        vehicle_id=vehicle,
        authorized_vehicle_id=vehicle,
        account_active=True,
        authenticated_session_active=True,
        eligibility_status="eligible",
        eligibility_expires_at=NOW + timedelta(hours=1),
        vehicle_approved=True,
        supported_services=frozenset({"immediate_standard"}),
        availability="available",
        availability_observed_at=NOW,
        earning_capability="ride_driver",
        fatigue_eligible=True,
        pickup_cost_seconds=eta,
        pickup_accessible=True,
        conflicting_commitment=False,
        active_workload_count=0,
        reliability_bps=5000,
        cancellation_history_bps=0,
        opportunity_deficit_bps=0,
        eligibility_policy_version="driver.eligibility.v1",
        temporary_restrictions_clear=True,
        traffic_evidence_fresh=True,
        pickup_confidence_bps=9000,
        route_evidence_id=f"rie-{uuid4()}",
        route_observed_at=NOW,
    )
    values.update(changes)
    return EligibleDriverInput.model_validate(values)


def test_dispatch_hard_filters_role_session_safety_fatigue_and_route_evidence() -> None:
    eligible = candidate(30)
    excluded = [
        candidate(1, authenticated_session_active=False),
        candidate(1, earning_capability="food_courier"),
        candidate(1, fatigue_eligible=False),
        candidate(1, temporary_restrictions_clear=False),
        candidate(1, traffic_evidence_fresh=False),
        candidate(1, pickup_confidence_bps=4999),
        candidate(1, active_workload_count=1, conflicting_commitment=True),
    ]
    ranked = rank_candidates([*excluded, eligible], now=NOW, max_age_seconds=45)
    assert [item.driver_id for item in ranked] == [eligible.driver_id]


def test_eta_remains_primary_with_bounded_explainable_fairness() -> None:
    fastest = candidate(20, reliability_bps=9000)
    fairly_close = candidate(27, opportunity_deficit_bps=6000, reliability_bps=8000)
    too_far = candidate(90, opportunity_deficit_bps=10000, reliability_bps=10000)
    ranked = rank_candidates(
        [too_far, fastest, fairly_close], now=NOW, max_age_seconds=45
    )
    assert ranked[0].driver_id == fairly_close.driver_id
    assert ranked[-1].driver_id == too_far.driver_id
    reasons = decision_reason_codes(ranked[0])
    assert {
        "pickup_eta_primary",
        "bounded_fair_opportunity",
        "route_intelligence_evidence",
    } <= set(reasons)


def test_new_driver_reputation_is_neutral_and_no_single_soft_signal_wins() -> None:
    neutral_new = candidate(25, reliability_bps=5000)
    established = candidate(24, reliability_bps=8000, cancellation_history_bps=500)
    ranked = rank_candidates([neutral_new, established], now=NOW, max_age_seconds=45)
    assert set(item.driver_id for item in ranked) == {
        neutral_new.driver_id,
        established.driver_id,
    }
    assert len(decision_reason_codes(neutral_new)) >= 5


def test_bounded_candidate_ranking_load_baseline() -> None:
    candidates = [candidate(20 + index) for index in range(20)]
    started = perf_counter()
    for _ in range(2_000):
        rank_candidates(candidates, now=NOW, max_age_seconds=45)
    elapsed = perf_counter() - started
    assert elapsed < 2.0


def test_dispatch_activation_is_fail_closed_without_production_approval() -> None:
    assert (
        Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
            _env_file=None
        ).CANONICAL_DISPATCH_ENABLED
        is False
    )
    with pytest.raises(ValidationError, match="production activation"):
        Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
            _env_file=None,
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            CANONICAL_DISPATCH_ENABLED=True,
        )
