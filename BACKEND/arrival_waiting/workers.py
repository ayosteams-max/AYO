from datetime import datetime
from typing import Any

from BACKEND.arrival_waiting.models import WaitingState


class ArrivalWaitingRecoveryWorker:
    """Bounded restart-safe deadline projection; never creates no-show evidence."""

    def __init__(self, uow_factory: Any, *, batch_size: int = 100) -> None:
        if not 1 <= batch_size <= 500:
            raise ValueError("Worker batch size must be between 1 and 500")
        self._uow_factory = uow_factory
        self._batch_size = batch_size

    def run_once(self, *, now: datetime) -> int:
        changed = 0
        with self._uow_factory() as unit:
            sessions = unit.arrival_waiting.claim_due_sessions(
                now=now, limit=self._batch_size
            )
            for session in sessions:
                if session.state is not WaitingState.FREE_WAIT_ACTIVE:
                    continue
                ending = session.model_copy(
                    update={
                        "state": WaitingState.FREE_WAIT_ENDING,
                        "version": session.version + 1,
                        "updated_at": now,
                        "reason_codes": (
                            "waiting.free_wait_expired_evaluation_required",
                        ),
                    }
                )
                unit.arrival_waiting.update_session(
                    ending, expected_version=session.version
                )
                changed += 1
        return changed
