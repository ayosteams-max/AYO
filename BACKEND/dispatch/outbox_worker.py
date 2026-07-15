import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from BACKEND.dispatch.outbox import OutboxPublisher
from BACKEND.dispatch.scheduler import WorkerHealth
from BACKEND.observability import MetricsSink, NullMetricsSink, safe_event
from BACKEND.persistence.composition import PostgresRepositoryComposition

logger = logging.getLogger("ayo.dispatch.outbox")


@dataclass(frozen=True, slots=True)
class OutboxRunResult:
    claimed: int
    published: int
    retried: int
    dead_lettered: int
    lag_seconds: float


class OutboxDeliveryWorker:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        publisher: OutboxPublisher,
        *,
        worker_id: str,
        metrics: MetricsSink | None = None,
        health: WorkerHealth | None = None,
        batch_limit: int = 100,
        stale_claim_seconds: int = 60,
        maximum_attempts: int = 5,
        base_backoff_seconds: int = 5,
        maximum_backoff_seconds: int = 300,
    ) -> None:
        if not 1 <= batch_limit <= 500:
            raise ValueError("Batch limit must be between 1 and 500")
        if not 1 <= maximum_attempts <= 20:
            raise ValueError("Maximum attempts must be between 1 and 20")
        if not 1 <= base_backoff_seconds <= maximum_backoff_seconds <= 3600:
            raise ValueError("Outbox backoff policy is invalid")
        self._composition = composition
        self._publisher = publisher
        self._worker_id = worker_id
        self._metrics = metrics or NullMetricsSink()
        self._health = health or WorkerHealth()
        self._batch_limit = batch_limit
        self._stale_claim_seconds = stale_claim_seconds
        self._maximum_attempts = maximum_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._maximum_backoff_seconds = maximum_backoff_seconds

    def run_once(self, *, now: datetime | None = None) -> OutboxRunResult:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        self._health.started(instant)
        try:
            with self._composition.unit_of_work() as unit:
                messages = unit.outbox.claim_ready(
                    worker_id=self._worker_id,
                    now=instant,
                    limit=self._batch_limit,
                    stale_after_seconds=self._stale_claim_seconds,
                )
        except Exception:
            self._health.failed("outbox_claim_failed")
            raise
        published = retried = dead_lettered = 0
        for message in messages:
            try:
                self._publisher.publish(message)
                with self._composition.unit_of_work() as unit:
                    if unit.outbox.mark_published(
                        message_id=message.message_id,
                        worker_id=self._worker_id,
                        published_at=instant,
                    ):
                        published += 1
                        safe_event(
                            logger,
                            event="dispatch_outbox_published",
                            outcome="success",
                            event_id=str(message.message_id),
                            worker_id=self._worker_id,
                        )
            except Exception:
                with self._composition.unit_of_work() as unit:
                    dead = unit.outbox.mark_failed(
                        message_id=message.message_id,
                        worker_id=self._worker_id,
                        failed_at=instant,
                        error_code="publisher_unavailable",
                        maximum_attempts=self._maximum_attempts,
                        base_backoff_seconds=self._base_backoff_seconds,
                        maximum_backoff_seconds=self._maximum_backoff_seconds,
                    )
                if dead:
                    dead_lettered += 1
                    self._metrics.increment("outbox_dead_letter_count")
                else:
                    retried += 1
                    self._metrics.increment("outbox_retry_count")
                safe_event(
                    logger,
                    event="dispatch_outbox_delivery",
                    outcome="dead_lettered" if dead else "retry_scheduled",
                    event_id=str(message.message_id),
                    worker_id=self._worker_id,
                    reason="publisher_unavailable",
                )
        with self._composition.unit_of_work() as unit:
            lag = unit.outbox.pending_lag_seconds(now=instant)
        self._metrics.gauge(
            "dispatch_worker_lag_seconds", lag, labels={"worker": "outbox"}
        )
        self._health.succeeded(instant)
        return OutboxRunResult(
            claimed=len(messages),
            published=published,
            retried=retried,
            dead_lettered=dead_lettered,
            lag_seconds=lag,
        )
