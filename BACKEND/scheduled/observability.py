import logging
from uuid import UUID

from BACKEND.observability import MetricsSink, NullMetricsSink, safe_event


class ScheduledObservability:
    """Privacy-safe scheduled metrics and logs; labels never contain personal data."""

    def __init__(
        self,
        metrics: MetricsSink | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._metrics = metrics or NullMetricsSink()
        self._logger = logger or logging.getLogger("ayo.scheduled")

    def outcome(
        self,
        metric: str,
        reservation_id: UUID,
        outcome: str,
        *,
        value: int = 1,
    ) -> None:
        approved = {
            "scheduled_reservation_creation",
            "scheduled_confirmation_outcomes",
            "scheduled_soft_replacements",
            "scheduled_replacement_suppressed",
            "scheduled_formal_commitments",
            "scheduled_reassignments",
            "scheduled_pre_dispatch_outcomes",
            "scheduled_airport_context_freshness",
            "scheduled_recovery_success",
            "scheduled_database_conflicts",
            "scheduled_authorization_failures",
            "scheduled_notification_delivery_attempts",
        }
        if metric not in approved:
            raise ValueError("Scheduled metric is not privacy approved")
        self._metrics.increment(metric, labels={"outcome": outcome}, value=value)
        safe_event(
            self._logger,
            event=metric,
            outcome=outcome,
            reservation_id=str(reservation_id),
        )

    def worker_lag(self, worker: str, seconds: float) -> None:
        self._metrics.gauge(
            "scheduled_worker_lag_seconds", seconds, labels={"worker": worker}
        )
