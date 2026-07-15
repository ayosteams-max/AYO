import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Protocol

from sqlalchemy import Engine, text

from BACKEND.dispatch.worker import DispatchRecoveryWorker, RecoveryResult
from BACKEND.observability import MetricsSink, NullMetricsSink, safe_event

logger = logging.getLogger("ayo.dispatch.recovery")
DISPATCH_RECOVERY_LOCK_ID = 18_412_138_359_126_355


class WorkerLock(Protocol):
    @contextmanager
    def acquire(self) -> Iterator[bool]: ...


class PostgresRecoveryWorkerLock:
    """Holds a transaction-scoped advisory lock for one bounded recovery run."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def acquire(self) -> Iterator[bool]:
        with self._engine.begin() as connection:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                    {"lock_id": DISPATCH_RECOVERY_LOCK_ID},
                ).scalar_one()
            )
            yield acquired


@dataclass(frozen=True, slots=True)
class WorkerHealthSnapshot:
    running: bool
    last_started_at: datetime | None
    last_succeeded_at: datetime | None
    last_failure_reason: str | None
    consecutive_failures: int
    skipped_overlap_count: int

    def ready(self, *, now: datetime, maximum_staleness_seconds: int = 300) -> bool:
        if (
            self.running
            or self.consecutive_failures > 0
            or self.last_succeeded_at is None
        ):
            return False
        return now - self.last_succeeded_at <= timedelta(
            seconds=maximum_staleness_seconds
        )


class WorkerHealth:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = WorkerHealthSnapshot(False, None, None, None, 0, 0)

    def started(self, at: datetime) -> None:
        with self._lock:
            self._snapshot = WorkerHealthSnapshot(
                True,
                at,
                self._snapshot.last_succeeded_at,
                self._snapshot.last_failure_reason,
                self._snapshot.consecutive_failures,
                self._snapshot.skipped_overlap_count,
            )

    def succeeded(self, at: datetime) -> None:
        with self._lock:
            self._snapshot = WorkerHealthSnapshot(
                False,
                self._snapshot.last_started_at,
                at,
                None,
                0,
                self._snapshot.skipped_overlap_count,
            )

    def failed(self, reason: str) -> None:
        with self._lock:
            self._snapshot = WorkerHealthSnapshot(
                False,
                self._snapshot.last_started_at,
                self._snapshot.last_succeeded_at,
                reason,
                self._snapshot.consecutive_failures + 1,
                self._snapshot.skipped_overlap_count,
            )

    def skipped(self) -> None:
        with self._lock:
            self._snapshot = WorkerHealthSnapshot(
                self._snapshot.running,
                self._snapshot.last_started_at,
                self._snapshot.last_succeeded_at,
                self._snapshot.last_failure_reason,
                self._snapshot.consecutive_failures,
                self._snapshot.skipped_overlap_count + 1,
            )

    def snapshot(self) -> WorkerHealthSnapshot:
        with self._lock:
            return self._snapshot


@dataclass(frozen=True, slots=True)
class ScheduledRecoveryResult:
    ran: bool
    recovery: RecoveryResult | None


class DispatchRecoveryCoordinator:
    def __init__(
        self,
        worker: DispatchRecoveryWorker,
        worker_lock: WorkerLock,
        health: WorkerHealth,
        *,
        metrics: MetricsSink | None = None,
        worker_id: str = "dispatch-recovery",
    ) -> None:
        self._worker = worker
        self._lock = worker_lock
        self._health = health
        self._metrics = metrics or NullMetricsSink()
        self._worker_id = worker_id

    def run_once(self, *, now: datetime | None = None) -> ScheduledRecoveryResult:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._lock.acquire() as acquired:
            if not acquired:
                self._health.skipped()
                self._metrics.increment("dispatch_worker_overlap_skipped")
                return ScheduledRecoveryResult(False, None)
            self._health.started(instant)
            try:
                result = self._worker.run_once(now=instant)
                self._health.succeeded(instant)
                self._metrics.increment(
                    "offer_expiry_count", value=result.expired_offers
                )
                self._metrics.increment(
                    "reassignment_count", value=result.resumed_searches
                )
                self._metrics.increment(
                    "no_driver_outcomes", value=result.abandoned_searches
                )
                safe_event(
                    logger,
                    event="dispatch_recovery_run",
                    outcome="success",
                    worker_id=self._worker_id,
                )
                return ScheduledRecoveryResult(True, result)
            except Exception:
                self._health.failed("recovery_failed")
                safe_event(
                    logger,
                    event="dispatch_recovery_run",
                    outcome="failed",
                    worker_id=self._worker_id,
                    reason="recovery_failed",
                )
                raise
