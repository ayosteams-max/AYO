from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from BACKEND.arrival_waiting.models import WaitingSession, WaitingState
from BACKEND.arrival_waiting.workers import ArrivalWaitingRecoveryWorker

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


class Repo:
    def __init__(self, item):
        self.item = item

    def claim_due_sessions(self, *, now, limit):
        del limit
        if (
            self.item.free_wait_deadline <= now
            and self.item.state is WaitingState.FREE_WAIT_ACTIVE
        ):
            return [self.item]
        return []

    def update_session(self, item, *, expected_version):
        assert self.item.version == expected_version
        self.item = item


class Unit:
    def __init__(self, repo):
        self.arrival_waiting = repo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def session():
    return WaitingSession(
        ride_id=uuid4(),
        assignment_id=uuid4(),
        arrival_evaluation_id=uuid4(),
        policy_snapshot_id=uuid4(),
        state=WaitingState.FREE_WAIT_ACTIVE,
        verified_arrival_at=NOW,
        started_at=NOW,
        free_wait_deadline=NOW + timedelta(seconds=10),
        updated_at=NOW,
        last_observation_sequence=1,
        reason_codes=("waiting.free_wait_started",),
    )


def test_worker_recovers_deadline_once_after_restart():
    repo = Repo(session())

    def factory():
        return Unit(repo)

    first_worker = ArrivalWaitingRecoveryWorker(factory, batch_size=10)
    assert first_worker.run_once(now=NOW + timedelta(seconds=11)) == 1
    restarted_worker = ArrivalWaitingRecoveryWorker(factory, batch_size=10)
    assert restarted_worker.run_once(now=NOW + timedelta(seconds=12)) == 0
    assert repo.item.state is WaitingState.FREE_WAIT_ENDING


def test_worker_is_bounded_and_ignores_not_due():
    repo = Repo(session())
    worker = ArrivalWaitingRecoveryWorker(lambda: Unit(repo))
    assert worker.run_once(now=NOW) == 0
    with pytest.raises(ValueError, match="batch size"):
        ArrivalWaitingRecoveryWorker(lambda: Unit(repo), batch_size=0)
