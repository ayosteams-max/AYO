import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, select, text, update

from BACKEND.dispatch.scheduler import WorkerHealth, WorkerHealthSnapshot
from BACKEND.observability import MetricsSink, NullMetricsSink, safe_event
from BACKEND.persistence.tables import reservation_checkpoints

logger = logging.getLogger("ayo.scheduled.worker")
SCHEDULED_WORKER_LOCK_BASE = 24_817_361_902_400_000


class ScheduledWorkerKind(StrEnum):
    PLANNING = "planning"
    DRIVER_COMMITMENT = "driver_commitment"
    REVALIDATION = "revalidation"
    SOFT_REPLACEMENT = "soft_replacement"
    FORMAL_REASSIGNMENT = "formal_reassignment"
    RESERVATION_EXPIRY = "reservation_expiry"
    PASSENGER_CONFIRMATION_EXPIRY = "passenger_confirmation_expiry"
    PRE_DISPATCH = "pre_dispatch"
    AIRPORT_REFRESH = "airport_refresh"
    RECOVERY = "recovery"
    OUTBOX_DELIVERY = "outbox_delivery"


@dataclass(frozen=True, slots=True)
class ClaimedCheckpoint:
    checkpoint_id: UUID
    reservation_id: UUID
    kind: ScheduledWorkerKind
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ScheduledWorkerResult:
    ran: bool
    claimed: int
    completed: int
    retried: int


class ScheduledCheckpointProcessor(Protocol):
    def process(self, checkpoint: ClaimedCheckpoint, *, now: datetime) -> None: ...


class PostgresScheduledWorkerLock:
    def __init__(self, engine: Engine, kind: ScheduledWorkerKind) -> None:
        self._engine = engine
        self._lock_id = SCHEDULED_WORKER_LOCK_BASE + list(ScheduledWorkerKind).index(
            kind
        )

    @contextmanager
    def acquire(self) -> Iterator[bool]:
        with self._engine.begin() as connection:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                    {"lock_id": self._lock_id},
                ).scalar_one()
            )
            yield acquired


class PostgresCheckpointClaims:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim(
        self,
        kind: ScheduledWorkerKind,
        *,
        worker_id: str,
        now: datetime,
        limit: int,
    ) -> list[ClaimedCheckpoint]:
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    select(reservation_checkpoints)
                    .where(
                        reservation_checkpoints.c.payload["kind"].astext == kind.value,
                        reservation_checkpoints.c.payload["due_at"].astext
                        <= now.isoformat(),
                        reservation_checkpoints.c.payload["completed_at"].astext.is_(
                            None
                        ),
                    )
                    .order_by(reservation_checkpoints.c.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            claimed: list[ClaimedCheckpoint] = []
            for row in rows:
                payload = dict(row["payload"])
                payload["claimed_by"] = worker_id
                payload["claimed_at"] = now.isoformat()
                payload["attempt_count"] = int(payload.get("attempt_count", 0)) + 1
                connection.execute(
                    update(reservation_checkpoints)
                    .where(
                        reservation_checkpoints.c.checkpoint_id == row["checkpoint_id"]
                    )
                    .values(payload=payload, version=row["version"] + 1)
                )
                claimed.append(
                    ClaimedCheckpoint(
                        checkpoint_id=row["checkpoint_id"],
                        reservation_id=row["reservation_id"],
                        kind=kind,
                        attempt_count=payload["attempt_count"],
                    )
                )
            return claimed

    def complete(self, checkpoint_id: UUID, *, now: datetime) -> None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(reservation_checkpoints)
                    .where(reservation_checkpoints.c.checkpoint_id == checkpoint_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            payload = dict(row["payload"])
            payload["completed_at"] = now.isoformat()
            connection.execute(
                update(reservation_checkpoints)
                .where(reservation_checkpoints.c.checkpoint_id == checkpoint_id)
                .values(payload=payload, version=row["version"] + 1)
            )


class ScheduledWorkerCoordinator:
    def __init__(
        self,
        kind: ScheduledWorkerKind,
        lock: PostgresScheduledWorkerLock,
        claims: PostgresCheckpointClaims,
        processor: ScheduledCheckpointProcessor,
        *,
        health: WorkerHealth | None = None,
        metrics: MetricsSink | None = None,
        worker_id: str,
        batch_limit: int = 100,
    ) -> None:
        if not 1 <= batch_limit <= 500:
            raise ValueError("Scheduled worker batch must be between 1 and 500")
        self._kind = kind
        self._lock = lock
        self._claims = claims
        self._processor = processor
        self._health = health or WorkerHealth()
        self._metrics = metrics or NullMetricsSink()
        self._worker_id = worker_id
        self._batch_limit = batch_limit

    def run_once(self, *, now: datetime | None = None) -> ScheduledWorkerResult:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._lock.acquire() as acquired:
            if not acquired:
                self._health.skipped()
                self._metrics.increment(
                    "scheduled_worker_overlap_skipped",
                    labels={"worker": self._kind.value},
                )
                return ScheduledWorkerResult(False, 0, 0, 0)
            self._health.started(instant)
            completed = retried = 0
            try:
                checkpoints = self._claims.claim(
                    self._kind,
                    worker_id=self._worker_id,
                    now=instant,
                    limit=self._batch_limit,
                )
                for checkpoint in checkpoints:
                    try:
                        self._processor.process(checkpoint, now=instant)
                        self._claims.complete(checkpoint.checkpoint_id, now=instant)
                        completed += 1
                    except Exception:
                        retried += 1
                self._health.succeeded(instant)
                self._metrics.gauge(
                    "scheduled_worker_lag_seconds",
                    0.0,
                    labels={"worker": self._kind.value},
                )
                safe_event(
                    logger,
                    event="scheduled_worker_run",
                    outcome="success",
                    worker_id=self._worker_id,
                )
                return ScheduledWorkerResult(True, len(checkpoints), completed, retried)
            except Exception:
                self._health.failed("scheduled_worker_failed")
                raise

    def health_snapshot(self) -> WorkerHealthSnapshot:
        return self._health.snapshot()


class ScheduledWorkerRegistry:
    """Explicit controlled scheduler boundary; construction never starts a worker."""

    def __init__(
        self, coordinators: dict[ScheduledWorkerKind, ScheduledWorkerCoordinator]
    ) -> None:
        missing = set(ScheduledWorkerKind) - set(coordinators)
        if missing:
            raise ValueError(
                "Every scheduled worker kind requires explicit composition"
            )
        self._coordinators = dict(coordinators)

    def run_once(
        self, kind: ScheduledWorkerKind, *, now: datetime | None = None
    ) -> ScheduledWorkerResult:
        return self._coordinators[kind].run_once(now=now)

    def health(self) -> dict[ScheduledWorkerKind, WorkerHealthSnapshot]:
        return {
            kind: coordinator.health_snapshot()
            for kind, coordinator in self._coordinators.items()
        }
