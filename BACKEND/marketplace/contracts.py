from typing import Protocol

from BACKEND.marketplace.models import (
    MarketplaceRecommendation,
    MarketplaceRuleSet,
    MarketplaceSnapshot,
)


class MarketplaceStrategy(Protocol):
    """Stable seam for deterministic authority and future shadow strategies."""

    def evaluate(
        self, snapshot: MarketplaceSnapshot, rules: MarketplaceRuleSet
    ) -> MarketplaceRecommendation: ...


class MarketplaceDecisionRepository(Protocol):
    def save_once(
        self, recommendation: MarketplaceRecommendation
    ) -> tuple[MarketplaceRecommendation, bool]: ...


class MarketplaceAdvisorySink(Protocol):
    def publish(self, recommendation: MarketplaceRecommendation) -> None: ...
