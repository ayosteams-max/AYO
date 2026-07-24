import logging
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import Engine

from BACKEND.persistence.health import DatabaseHealthChecker
from BACKEND.persistence.logging import database_event
from BACKEND.persistence.migrations import SchemaVersionReadinessChecker

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeReadiness:
    ready: bool
    database: str
    schema: str
    reason: str | None = None


class EngineeringRuntime:
    """Own process-scoped foundation resources and fail-safe probe state."""

    def __init__(
        self,
        engine: Engine | None = None,
        *,
        persistence_required: bool = False,
    ) -> None:
        if persistence_required and engine is None:
            raise RuntimeError("Required persistence has no configured database engine")
        self._engine = engine
        self._persistence_required = persistence_required
        self._started = False
        self._stopping = False
        self._closed = False

    @property
    def live(self) -> bool:
        return not self._stopping and not self._closed

    def readiness(self) -> RuntimeReadiness:
        if not self._started:
            return RuntimeReadiness(False, "unknown", "unknown", "not_started")
        if self._stopping or self._closed:
            return RuntimeReadiness(False, "unknown", "unknown", "stopping")
        if self._engine is None:
            return RuntimeReadiness(True, "not_required", "not_required")

        database = DatabaseHealthChecker(self._engine).check()
        if not database.ready:
            return RuntimeReadiness(
                False, "unavailable", "unknown", "database_unavailable"
            )
        schema = SchemaVersionReadinessChecker(self._engine).check()
        if not schema.ready:
            return RuntimeReadiness(False, "ready", "not_ready", schema.reason)
        return RuntimeReadiness(True, "ready", "ready")

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("Engineering runtime cannot restart after shutdown")
        if self._started:
            return
        started = perf_counter()
        self._started = True
        readiness = self.readiness()
        database_event(
            logger,
            "application.startup_validation",
            "ready" if readiness.ready else "not_ready",
            (perf_counter() - started) * 1_000,
            persistence_required=self._persistence_required,
            reason=readiness.reason,
        )
        if self._persistence_required and not readiness.ready:
            self._started = False
            raise RuntimeError(
                f"Required persistence failed startup validation: {readiness.reason}"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._stopping = True
        started = perf_counter()
        try:
            if self._engine is not None:
                self._engine.dispose()
        finally:
            self._closed = True
            database_event(
                logger,
                "application.shutdown",
                "completed",
                (perf_counter() - started) * 1_000,
                persistence_required=self._persistence_required,
            )
