import logging

from BACKEND.marketplace.contracts import (
    MarketplaceAdvisorySink,
    MarketplaceDecisionRepository,
    MarketplaceStrategy,
)
from BACKEND.marketplace.models import (
    MarketplaceRecommendation,
    MarketplaceRuleSet,
    MarketplaceSnapshot,
)
from BACKEND.observability import MetricsSink, NullMetricsSink, safe_event


class MarketplaceAdvisoryApplication:
    """Failure-isolated advisory application; callers never depend on its success."""

    def __init__(
        self,
        strategy: MarketplaceStrategy,
        repository: MarketplaceDecisionRepository,
        sink: MarketplaceAdvisorySink,
        *,
        metrics: MetricsSink | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._strategy = strategy
        self._repository = repository
        self._sink = sink
        self._metrics = metrics or NullMetricsSink()
        self._logger = logger or logging.getLogger(__name__)

    def advise(
        self, snapshot: MarketplaceSnapshot, rules: MarketplaceRuleSet
    ) -> MarketplaceRecommendation | None:
        try:
            recommendation = self._strategy.evaluate(snapshot, rules)
            stored, created = self._repository.save_once(recommendation)
            if created:
                self._sink.publish(stored)
            self._metrics.increment(
                "marketplace_recommendations",
                labels={"type": stored.recommendation.value},
            )
            self._metrics.gauge(
                "marketplace_health_score", float(stored.health_score_bps)
            )
            self._metrics.gauge(
                "marketplace_demand_forecast",
                float(stored.demand_forecast.expected_requests),
                labels={"quality": stored.quality.value},
            )
            for component in stored.components:
                self._metrics.gauge(
                    "marketplace_component_score",
                    float(component.score_bps),
                    labels={"component": component.code},
                )
            safe_event(
                self._logger,
                event="marketplace_recommendation",
                outcome="created" if created else "replayed",
                event_id=str(stored.decision_id),
            )
            return stored
        except Exception:  # advisory isolation boundary
            self._metrics.increment("marketplace_evaluation_failures")
            safe_event(
                self._logger,
                event="marketplace_evaluation",
                outcome="failed",
                reason="advisory_failure",
            )
            return None
