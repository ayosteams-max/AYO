from datetime import UTC, datetime, timedelta
from time import perf_counter
from tracemalloc import get_traced_memory, start, stop

from BACKEND.marketplace.engine import DeterministicMarketplaceStrategy
from BACKEND.marketplace.models import MarketplaceRuleSet, MarketplaceSnapshot


def test_ten_thousand_deterministic_evaluations_meet_approved_budget() -> None:
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    rules = MarketplaceRuleSet(version="benchmark.v1", effective_at=now)
    snapshot = MarketplaceSnapshot(
        market_code="et.addis",
        zone_code="bole",
        service_type="ayo.go",
        window_started_at=now - timedelta(minutes=15),
        window_ended_at=now,
        request_count=100,
        assigned_count=90,
        completed_count=85,
        no_driver_count=5,
        rider_cancel_count=3,
        driver_cancel_count=2,
        pickup_wait_p90_seconds=500,
        eligible_driver_count=80,
        online_driver_count=90,
        driver_idle_p50_seconds=900,
        driver_deadhead_p50_seconds=400,
        opportunity_bottom_decile_minor=7_000,
        opportunity_median_minor=10_000,
        estimated_contribution_minor=1_000,
        forecast_baseline_requests=100,
        sample_size=100,
    )
    strategy = DeterministicMarketplaceStrategy()
    began = perf_counter()
    signatures = {
        (
            result.health_score_bps,
            result.recommendation,
        )
        for result in (strategy.evaluate(snapshot, rules) for _ in range(10_000))
    }
    duration = perf_counter() - began
    start()
    _ = [strategy.evaluate(snapshot, rules) for _ in range(1_000)]
    _, peak = get_traced_memory()
    stop()
    print(
        f"marketplace_benchmark duration_seconds={duration:.6f} "
        f"peak_sample_bytes={peak}"
    )
    assert duration < 10
    assert peak < 256 * 1024 * 1024
    assert len(signatures) == 1
