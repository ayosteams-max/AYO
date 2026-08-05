from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from BACKEND.marketplace.application import MarketplaceAdvisoryApplication
from BACKEND.marketplace.engine import (
    DeterministicMarketplaceStrategy,
    attribute_cancellation,
    balance_driver_idle_time,
    balance_driver_opportunities,
    protect_external_delay,
)
from BACKEND.marketplace.memory import (
    InMemoryMarketplaceAdvisorySink,
    InMemoryMarketplaceDecisionRepository,
)
from BACKEND.marketplace.models import (
    CancellationCause,
    CancellationEvidence,
    CancellationParty,
    ContextSignal,
    DataQuality,
    DelayEvidence,
    DriverOpportunity,
    MarketplaceRuleSet,
    MarketplaceSnapshot,
    RecommendationType,
    SignalKind,
)
from BACKEND.marketplace.simulation import MarketplaceSimulationRunner
from BACKEND.observability import InMemoryMetricsSink

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def rules(**overrides) -> MarketplaceRuleSet:
    values = {"version": "marketplace.v1", "effective_at": NOW}
    values.update(overrides)
    return MarketplaceRuleSet.model_validate(values)


def snapshot(**overrides) -> MarketplaceSnapshot:
    values = {
        "market_code": "et.addis",
        "zone_code": "bole",
        "service_type": "ayo.go",
        "window_started_at": NOW - timedelta(minutes=15),
        "window_ended_at": NOW,
        "request_count": 100,
        "assigned_count": 94,
        "completed_count": 90,
        "no_driver_count": 4,
        "rider_cancel_count": 3,
        "driver_cancel_count": 2,
        "pickup_wait_p90_seconds": 480,
        "eligible_driver_count": 90,
        "online_driver_count": 95,
        "driver_idle_p50_seconds": 900,
        "driver_deadhead_p50_seconds": 400,
        "opportunity_bottom_decile_minor": 7_000,
        "opportunity_median_minor": 10_000,
        "estimated_contribution_minor": 5_000,
        "forecast_baseline_requests": 100,
        "sample_size": 100,
    }
    values.update(overrides)
    return MarketplaceSnapshot.model_validate(values)


def test_healthy_market_is_scored_and_explained_deterministically() -> None:
    strategy = DeterministicMarketplaceStrategy()
    result = strategy.evaluate(snapshot(), rules())
    replay = strategy.evaluate(snapshot(snapshot_id=result.snapshot_id), rules())
    assert result.health_score_bps >= 7_000
    assert result.recommendation is RecommendationType.NO_CHANGE
    assert result.rule_version == "marketplace.v1"
    assert {item.code for item in result.components} == {
        "rider_reliability",
        "driver_fairness",
        "marketplace_efficiency",
        "business_sustainability",
    }
    assert result.health_score_bps == replay.health_score_bps


def test_demand_contexts_are_capped_and_emergency_suppresses_surge_review() -> None:
    signal = ContextSignal(
        kind=SignalKind.WEATHER,
        code="heavy_rain",
        factor_bps=20_000,
        confidence_bps=10_000,
        observed_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        emergency=True,
    )
    result = DeterministicMarketplaceStrategy().evaluate(
        snapshot(
            eligible_driver_count=5,
            pickup_wait_p90_seconds=1_500,
            signals=(signal,),
        ),
        rules(demand_signal_cap_bps=13_000),
    )
    assert result.demand_forecast.factor_bps == 13_000
    assert result.demand_forecast.context_codes == ("weather", "heavy_rain")
    assert result.recommendation is RecommendationType.SUPPRESS
    assert "emergency_price_review_suppressed" in result.reason_codes


def test_stale_signal_is_ignored_and_sparse_data_never_invents_precision() -> None:
    stale = ContextSignal(
        kind=SignalKind.EVENT,
        code="stadium_exit",
        factor_bps=15_000,
        confidence_bps=10_000,
        observed_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
    )
    result = DeterministicMarketplaceStrategy().evaluate(
        snapshot(sample_size=2, signals=(stale,)), rules()
    )
    assert result.quality is DataQuality.INSUFFICIENT
    assert result.demand_forecast.factor_bps == 10_000
    assert result.recommendation is RecommendationType.INSUFFICIENT_DATA


def test_opportunity_balance_only_compares_materially_equivalent_pickups() -> None:
    low_opportunity = DriverOpportunity(
        driver_id=uuid4(),
        completed_trips=0,
        pickup_eta_seconds=100,
        eligible_online_seconds=3_600,
        idle_seconds=1_800,
        offered_earnings_minor=2_000,
    )
    high_opportunity = DriverOpportunity(
        driver_id=uuid4(),
        completed_trips=100,
        pickup_eta_seconds=110,
        eligible_online_seconds=3_600,
        idle_seconds=100,
        offered_earnings_minor=10_000,
    )
    too_slow = DriverOpportunity(
        driver_id=uuid4(),
        completed_trips=100,
        pickup_eta_seconds=180,
        eligible_online_seconds=3_600,
        idle_seconds=3_000,
        offered_earnings_minor=0,
    )
    result = balance_driver_opportunities(
        [low_opportunity, high_opportunity, too_slow], rules()
    )
    assert {item.driver_id for item in result} == {
        low_opportunity.driver_id,
        high_opportunity.driver_id,
    }
    low = next(item for item in result if item.driver_id == low_opportunity.driver_id)
    assert low.credit_bps == 1_500
    assert low.neutral_reputation is True
    assert "neutral_new_driver" in low.reason_codes
    idle = balance_driver_idle_time(
        [low_opportunity, high_opportunity, too_slow], rules()
    )
    assert {item.driver_id for item in idle} == {
        low_opportunity.driver_id,
        high_opportunity.driver_id,
    }
    assert idle[0].driver_id == low_opportunity.driver_id


@pytest.mark.parametrize(
    ("evidence", "party", "cause", "protected"),
    [
        (
            CancellationEvidence(
                cancelled_by=CancellationParty.DRIVER,
                external_signal_confidence_bps=8_000,
            ),
            CancellationParty.EXTERNAL,
            CancellationCause.EXTERNAL_DISRUPTION,
            True,
        ),
        (
            CancellationEvidence(
                cancelled_by=CancellationParty.DRIVER, communication_failed=True
            ),
            CancellationParty.PLATFORM,
            CancellationCause.COMMUNICATION_FAILURE,
            True,
        ),
        (
            CancellationEvidence(
                cancelled_by=CancellationParty.DRIVER, pickup_ambiguous=True
            ),
            CancellationParty.PLATFORM,
            CancellationCause.PICKUP_AMBIGUITY,
            True,
        ),
        (
            CancellationEvidence(
                cancelled_by=CancellationParty.DRIVER, eta_error_seconds=180
            ),
            CancellationParty.PLATFORM,
            CancellationCause.ETA_MISS,
            True,
        ),
        (
            CancellationEvidence(cancelled_by=CancellationParty.DRIVER),
            CancellationParty.DRIVER,
            CancellationCause.DRIVER_AVOIDABLE,
            False,
        ),
    ],
)
def test_cancellation_attribution_is_causal_and_driver_protective(
    evidence, party, cause, protected
) -> None:
    result = attribute_cancellation(evidence)
    assert (result.responsible_party, result.cause) == (party, cause)
    assert result.protected_from_driver_penalty is protected


def test_external_delay_protection_favors_driver_when_verified() -> None:
    protected = protect_external_delay(
        DelayEvidence(
            expected_seconds=300,
            actual_seconds=600,
            signal_kind=SignalKind.TRAFFIC,
            confidence_bps=8_000,
        ),
        rules(),
    )
    unverified = protect_external_delay(
        DelayEvidence(expected_seconds=300, actual_seconds=600), rules()
    )
    assert protected.protected is True
    assert protected.protected_seconds == 300
    assert unverified.protected is False
    assert unverified.protected_seconds == 0


def test_advisory_failure_is_isolated_and_never_raises() -> None:
    class BrokenStrategy:
        def evaluate(self, snapshot, rules):
            del snapshot, rules
            raise RuntimeError("provider detail must not escape")

    metrics = InMemoryMetricsSink()
    application = MarketplaceAdvisoryApplication(
        BrokenStrategy(),
        InMemoryMarketplaceDecisionRepository(),
        InMemoryMarketplaceAdvisorySink(),
        metrics=metrics,
    )
    assert application.advise(snapshot(), rules()) is None
    assert metrics.counters[("marketplace_evaluation_failures", ())] == 1


def test_concurrent_retries_create_one_advisory_and_one_publication() -> None:
    repository = InMemoryMarketplaceDecisionRepository()
    sink = InMemoryMarketplaceAdvisorySink()
    application = MarketplaceAdvisoryApplication(
        DeterministicMarketplaceStrategy(), repository, sink
    )
    current_snapshot = snapshot()
    current_rules = rules()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: application.advise(current_snapshot, current_rules), range(40)
            )
        )
    assert all(item is not None for item in results)
    assert len({item.decision_id for item in results if item is not None}) == 1
    assert len(sink.items) == 1


def test_simulation_is_replayable_and_reports_candidate_changes() -> None:
    runner = MarketplaceSimulationRunner(DeterministicMarketplaceStrategy())
    result = runner.run(
        [snapshot(), snapshot(eligible_driver_count=5, pickup_wait_p90_seconds=1_500)],
        baseline=rules(version="baseline.v1", surge_supply_ratio_bps=100),
        candidate=rules(version="candidate.v1", surge_supply_ratio_bps=9_000),
        dataset_checksum="a" * 64,
    )
    assert result.evaluated_snapshots == 2
    assert result.changed_recommendations >= 1
    assert result.deterministic_replay is True
    assert result.duration_microseconds >= 0
