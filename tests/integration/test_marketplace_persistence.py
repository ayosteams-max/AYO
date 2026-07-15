from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from BACKEND.marketplace.engine import DeterministicMarketplaceStrategy
from BACKEND.marketplace.models import MarketplaceRuleSet, MarketplaceSnapshot
from BACKEND.marketplace.simulation import MarketplaceSimulationRunner
from BACKEND.persistence.marketplace_repository import PostgresMarketplaceRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def rules(version: str) -> MarketplaceRuleSet:
    return MarketplaceRuleSet(version=version, effective_at=NOW)


def snapshot() -> MarketplaceSnapshot:
    return MarketplaceSnapshot(
        market_code="et.addis",
        zone_code="bole",
        service_type="ayo.go",
        window_started_at=NOW - timedelta(minutes=15),
        window_ended_at=NOW,
        request_count=100,
        assigned_count=90,
        completed_count=85,
        no_driver_count=5,
        rider_cancel_count=3,
        driver_cancel_count=2,
        pickup_wait_p90_seconds=500,
        eligible_driver_count=80,
        online_driver_count=90,
        driver_idle_p50_seconds=1_000,
        driver_deadhead_p50_seconds=400,
        opportunity_bottom_decile_minor=7_000,
        opportunity_median_minor=10_000,
        estimated_contribution_minor=1_000,
        forecast_baseline_requests=100,
        sample_size=100,
    )


def test_rule_decision_and_simulation_are_immutable_and_retry_safe(
    postgres_engine,
) -> None:
    current_rules = rules("marketplace.v1")
    current_snapshot = snapshot()
    decision = DeterministicMarketplaceStrategy().evaluate(
        current_snapshot, current_rules
    )
    with postgres_engine.begin() as connection:
        repository = PostgresMarketplaceRepository(connection)
        repository.add_rule_set(current_rules)
        assert repository.get_rule_set("marketplace.v1") == current_rules
        stored, created = repository.save_decision_once(
            decision,
            (
                current_snapshot.market_code,
                current_snapshot.zone_code,
                current_snapshot.service_type,
                current_snapshot.window_ended_at,
            ),
        )
        replay, replay_created = repository.save_decision_once(
            decision.model_copy(update={"decision_id": uuid4()}),
            (
                current_snapshot.market_code,
                current_snapshot.zone_code,
                current_snapshot.service_type,
                current_snapshot.window_ended_at,
            ),
        )
        assert created is True
        assert replay_created is False
        assert replay.decision_id == stored.decision_id

        simulation = MarketplaceSimulationRunner(
            DeterministicMarketplaceStrategy()
        ).run(
            [current_snapshot],
            baseline=current_rules,
            candidate=current_rules.model_copy(
                update={"rule_set_id": uuid4(), "version": "candidate.v1"}
            ),
            dataset_checksum="b" * 64,
        )
        assert repository.save_simulation(simulation) == simulation


def test_concurrent_decision_retries_persist_one_logical_result(
    postgres_engine,
) -> None:
    current_rules = rules("marketplace.concurrent.v1")
    current_snapshot = snapshot()
    with postgres_engine.begin() as connection:
        PostgresMarketplaceRepository(connection).add_rule_set(current_rules)

    def save(_: int):
        decision = DeterministicMarketplaceStrategy().evaluate(
            current_snapshot, current_rules
        )
        with postgres_engine.begin() as connection:
            return PostgresMarketplaceRepository(connection).save_decision_once(
                decision,
                (
                    current_snapshot.market_code,
                    current_snapshot.zone_code,
                    current_snapshot.service_type,
                    current_snapshot.window_ended_at,
                ),
            )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(save, range(16)))
    assert sum(created for _, created in results) == 1
    assert len({item.decision_id for item, _ in results}) == 1
