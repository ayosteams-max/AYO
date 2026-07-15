from collections.abc import Iterable
from datetime import UTC, datetime
from time import perf_counter_ns
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.marketplace.contracts import MarketplaceStrategy
from BACKEND.marketplace.models import (
    MarketplaceRecommendation,
    MarketplaceRuleSet,
    MarketplaceSnapshot,
    RecommendationType,
)


class SimulationRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID = Field(default_factory=uuid4)
    baseline_rule_version: str
    candidate_rule_version: str
    dataset_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_snapshots: int = Field(ge=0)
    changed_recommendations: int = Field(ge=0)
    baseline_health_bps: int = Field(ge=0, le=10_000)
    candidate_health_bps: int = Field(ge=0, le=10_000)
    candidate_price_review_count: int = Field(ge=0)
    candidate_suppression_count: int = Field(ge=0)
    deterministic_replay: bool
    duration_microseconds: int = Field(ge=0)
    completed_at: datetime


class MarketplaceSimulationRunner:
    def __init__(self, strategy: MarketplaceStrategy) -> None:
        self._strategy = strategy

    def run(
        self,
        snapshots: Iterable[MarketplaceSnapshot],
        *,
        baseline: MarketplaceRuleSet,
        candidate: MarketplaceRuleSet,
        dataset_checksum: str,
    ) -> SimulationRun:
        started = perf_counter_ns()
        materialized = tuple(snapshots)
        baseline_results = tuple(
            self._strategy.evaluate(snapshot, baseline) for snapshot in materialized
        )
        candidate_results = tuple(
            self._strategy.evaluate(snapshot, candidate) for snapshot in materialized
        )
        replay_results = tuple(
            self._strategy.evaluate(snapshot, candidate) for snapshot in materialized
        )
        changed = sum(
            left.recommendation != right.recommendation
            for left, right in zip(baseline_results, candidate_results, strict=True)
        )
        duration = (perf_counter_ns() - started) // 1_000
        return SimulationRun(
            baseline_rule_version=baseline.version,
            candidate_rule_version=candidate.version,
            dataset_checksum=dataset_checksum,
            evaluated_snapshots=len(materialized),
            changed_recommendations=changed,
            baseline_health_bps=self._average_health(baseline_results),
            candidate_health_bps=self._average_health(candidate_results),
            candidate_price_review_count=sum(
                item.recommendation is RecommendationType.PRICE_REVIEW
                for item in candidate_results
            ),
            candidate_suppression_count=sum(
                item.recommendation is RecommendationType.SUPPRESS
                for item in candidate_results
            ),
            deterministic_replay=self._canonical(candidate_results)
            == self._canonical(replay_results),
            duration_microseconds=duration,
            completed_at=datetime.now(UTC),
        )

    @staticmethod
    def _average_health(results: tuple[MarketplaceRecommendation, ...]) -> int:
        if not results:
            return 0
        return sum(item.health_score_bps for item in results) // len(results)

    @staticmethod
    def _canonical(
        results: tuple[MarketplaceRecommendation, ...],
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                item.snapshot_id,
                item.rule_set_id,
                item.health_score_bps,
                item.components,
                item.demand_forecast,
                item.recommendation,
                item.reason_codes,
                item.quality,
            )
            for item in results
        )
