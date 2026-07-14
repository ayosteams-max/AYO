from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    ready: bool
    latency_ms: float
    error_category: str | None = None


class DatabaseHealthChecker:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> DatabaseHealth:
        started = perf_counter()
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            return DatabaseHealth(
                ready=False,
                latency_ms=(perf_counter() - started) * 1_000,
                error_category=type(error).__name__,
            )
        return DatabaseHealth(
            ready=True,
            latency_ms=(perf_counter() - started) * 1_000,
        )
