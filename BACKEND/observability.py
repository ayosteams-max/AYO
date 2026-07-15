import logging
from collections import Counter
from collections.abc import Mapping
from threading import Lock
from typing import Protocol


class MetricsSink(Protocol):
    def increment(
        self, name: str, *, labels: Mapping[str, str] | None = None, value: int = 1
    ) -> None: ...

    def gauge(
        self, name: str, value: float, *, labels: Mapping[str, str] | None = None
    ) -> None: ...


class NullMetricsSink:
    def increment(
        self, name: str, *, labels: Mapping[str, str] | None = None, value: int = 1
    ) -> None:
        del name, labels, value

    def gauge(
        self, name: str, value: float, *, labels: Mapping[str, str] | None = None
    ) -> None:
        del name, value, labels


class InMemoryMetricsSink:
    """Thread-safe local/test collector; never a production metrics authority."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self.gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    @staticmethod
    def _key(
        name: str, labels: Mapping[str, str] | None
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted((labels or {}).items()))

    def increment(
        self, name: str, *, labels: Mapping[str, str] | None = None, value: int = 1
    ) -> None:
        if value < 0:
            raise ValueError("Metric increment cannot be negative")
        with self._lock:
            self.counters[self._key(name, labels)] += value

    def gauge(
        self, name: str, value: float, *, labels: Mapping[str, str] | None = None
    ) -> None:
        with self._lock:
            self.gauges[self._key(name, labels)] = value


def safe_event(logger: logging.Logger, *, event: str, outcome: str, **ids: str) -> None:
    allowed = {
        "correlation_id",
        "ride_id",
        "reservation_id",
        "event_id",
        "worker_id",
        "reason",
    }
    if set(ids) - allowed:
        raise ValueError("Structured log field is not privacy approved")
    logger.info(event, extra={"event": event, "outcome": outcome, **ids})
