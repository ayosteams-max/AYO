from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, select, text, update

from BACKEND.dispatch.scheduler import WorkerHealth, WorkerHealthSnapshot
from BACKEND.persistence.tables import active_ride_recovery_checkpoints


class ActiveRideWorkerKind(StrEnum):
    STALE_RIDE = "stale_ride"
    LIFECYCLE_RECOVERY = "lifecycle_recovery"
    PENDING_COMMAND = "pending_command"
    PICKUP_PIN_EXPIRY = "pickup_pin_expiry"
    NO_SHOW_TIMER = "no_show_timer"
    CONFIDENCE_REEVALUATION = "confidence_reevaluation"
    PICKUP_RECOMMENDATION_EXPIRY = "pickup_recommendation_expiry"
    OUTBOX_PROCESSING = "outbox_processing"
    PROJECTION_REPAIR = "projection_repair"


@dataclass(frozen=True, slots=True)
class ActiveRideCheckpoint:
    checkpoint_id: UUID
    ride_id: UUID
    kind: ActiveRideWorkerKind
    attempt_count: int


@dataclass(frozen=True, slots=True)
class WorkerResult:
    ran: bool
    claimed: int
    completed: int
    retried: int


class Processor(Protocol):
    def process(self, checkpoint: ActiveRideCheckpoint, *, now: datetime) -> None: ...


class ActiveRideWorker:
    LOCK_BASE = 24_817_361_903_000_000

    def __init__(
        self,
        engine: Engine,
        kind: ActiveRideWorkerKind,
        processor: Processor,
        *,
        worker_id: str,
        batch_limit: int = 100,
        health: WorkerHealth | None = None,
    ) -> None:
        if not 1 <= batch_limit <= 500:
            raise ValueError("Active ride worker batch must be between 1 and 500")
        self._engine = engine
        self._kind = kind
        self._processor = processor
        self._worker_id = worker_id
        self._batch_limit = batch_limit
        self._health = health or WorkerHealth()

    @contextmanager
    def _lock(self) -> Iterator[bool]:
        with self._engine.begin() as connection:
            lock_id = self.LOCK_BASE + list(ActiveRideWorkerKind).index(self._kind)
            yield bool(
                connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": lock_id}
                ).scalar_one()
            )

    def run_once(self, *, now: datetime | None = None) -> WorkerResult:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._lock() as acquired:
            if not acquired:
                self._health.skipped()
                return WorkerResult(False, 0, 0, 0)
            self._health.started(instant)
            with self._engine.begin() as connection:
                rows = (
                    connection.execute(
                        select(active_ride_recovery_checkpoints)
                        .where(
                            active_ride_recovery_checkpoints.c.kind == self._kind.value,
                            active_ride_recovery_checkpoints.c.due_at <= instant,
                            active_ride_recovery_checkpoints.c.completed_at.is_(None),
                        )
                        .order_by(active_ride_recovery_checkpoints.c.due_at)
                        .limit(self._batch_limit)
                        .with_for_update(skip_locked=True)
                    )
                    .mappings()
                    .all()
                )
                checkpoints = []
                for row in rows:
                    attempt = row["attempt_count"] + 1
                    connection.execute(
                        update(active_ride_recovery_checkpoints)
                        .where(
                            active_ride_recovery_checkpoints.c.checkpoint_id
                            == row["checkpoint_id"]
                        )
                        .values(
                            claimed_by=self._worker_id,
                            claimed_at=instant,
                            attempt_count=attempt,
                        )
                    )
                    checkpoints.append(
                        ActiveRideCheckpoint(
                            row["checkpoint_id"], row["ride_id"], self._kind, attempt
                        )
                    )
            completed = retried = 0
            for item in checkpoints:
                try:
                    self._processor.process(item, now=instant)
                    with self._engine.begin() as connection:
                        connection.execute(
                            update(active_ride_recovery_checkpoints)
                            .where(
                                active_ride_recovery_checkpoints.c.checkpoint_id
                                == item.checkpoint_id
                            )
                            .values(completed_at=instant)
                        )
                    completed += 1
                except Exception:
                    retried += 1
            self._health.succeeded(instant)
            return WorkerResult(True, len(checkpoints), completed, retried)

    def health(self) -> WorkerHealthSnapshot:
        return self._health.snapshot()


class ActiveRideWorkerRegistry:
    """Controlled scheduler composition; construction never starts background work."""

    def __init__(self, workers: dict[ActiveRideWorkerKind, ActiveRideWorker]) -> None:
        missing = set(ActiveRideWorkerKind) - set(workers)
        if missing:
            raise ValueError(
                "Every active ride worker kind requires explicit composition"
            )
        self._workers = dict(workers)

    def run_once(
        self, kind: ActiveRideWorkerKind, *, now: datetime | None = None
    ) -> WorkerResult:
        return self._workers[kind].run_once(now=now)

    def health(self) -> dict[ActiveRideWorkerKind, WorkerHealthSnapshot]:
        return {kind: worker.health() for kind, worker in self._workers.items()}
