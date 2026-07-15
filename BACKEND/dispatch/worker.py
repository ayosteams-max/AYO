from dataclasses import dataclass
from datetime import UTC, datetime

from BACKEND.dispatch.application import DispatchApplication


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    expired_offers: int
    resumed_searches: int
    abandoned_searches: int


class DispatchRecoveryWorker:
    """Scheduler-neutral, bounded and retry-safe recovery worker entry point."""

    def __init__(
        self, application: DispatchApplication, *, batch_limit: int = 100
    ) -> None:
        if not 1 <= batch_limit <= 1_000:
            raise ValueError("Batch limit must be between 1 and 1000")
        self._application = application
        self._batch_limit = batch_limit

    def run_once(self, *, now: datetime | None = None) -> RecoveryResult:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        expired, resumed, abandoned = self._application.recover(
            now=instant, limit=self._batch_limit
        )
        return RecoveryResult(expired, resumed, abandoned)
