from threading import Lock

from BACKEND.marketplace.models import MarketplaceRecommendation


class InMemoryMarketplaceDecisionRepository:
    """Thread-safe test/local adapter; never production authority."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._items: dict[tuple[object, ...], MarketplaceRecommendation] = {}

    @staticmethod
    def _key(item: MarketplaceRecommendation) -> tuple[object, ...]:
        return item.snapshot_id, item.rule_set_id

    def save_once(
        self, recommendation: MarketplaceRecommendation
    ) -> tuple[MarketplaceRecommendation, bool]:
        with self._lock:
            key = self._key(recommendation)
            existing = self._items.get(key)
            if existing is not None:
                return existing, False
            self._items[key] = recommendation
            return recommendation, True


class InMemoryMarketplaceAdvisorySink:
    def __init__(self) -> None:
        self._lock = Lock()
        self.items: dict[object, MarketplaceRecommendation] = {}

    def publish(self, recommendation: MarketplaceRecommendation) -> None:
        with self._lock:
            self.items.setdefault(recommendation.decision_id, recommendation)
