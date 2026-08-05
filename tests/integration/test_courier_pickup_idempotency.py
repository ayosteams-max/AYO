from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.idempotency import CourierPickupReplaySnapshotV1
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupRecord,
    CourierPickupState,
    CourierPickupView,
)
from BACKEND.persistence.courier_pickup_repository import (
    PostgresCourierPickupRepository,
)
from BACKEND.persistence.tables import commerce_courier_pickup_idempotency

pytestmark = pytest.mark.integration

ACTOR = UUID("20000000-0000-4000-8000-000000000001")
PICKUP = UUID("20000000-0000-4000-8000-000000000002")
ASSIGNMENT = UUID("20000000-0000-4000-8000-000000000003")
NOW = datetime(2026, 8, 5, tzinfo=UTC)


def snapshot() -> dict:
    record = CourierPickupRecord(
        pickup_id=PICKUP,
        dispatch_id=UUID(int=4),
        assignment_id=ASSIGNMENT,
        assignment_version=1,
        attempt_number=1,
        order_id=UUID(int=5),
        merchant_id=UUID(int=6),
        assigned_courier_identity_id=ACTOR,
        assignment_message_id=UUID(int=7),
        state=CourierPickupState.TRAVELLING,
        version=2,
        assigned_at=NOW,
        travelling_at=NOW,
        arrived_at=None,
        merchant_acknowledged_at=None,
        waiting_duration_seconds=None,
        updated_at=NOW,
    )
    return CourierPickupReplaySnapshotV1(
        response=CourierPickupView(pickup=record, events=(), evidence=())
    ).encode()


@pytest.fixture(autouse=True)
def clean_rows(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(delete(commerce_courier_pickup_idempotency))
    yield
    with postgres_engine.begin() as connection:
        connection.execute(delete(commerce_courier_pickup_idempotency))


def completed_row(*, request_hash: str = "a" * 64) -> dict:
    return {
        "actor_identity_id": ACTOR,
        "pickup_id": PICKUP,
        "action": CourierPickupAction.START_TRAVEL.value,
        "idempotency_key": "postgres-idempotency-0001",
        "request_hash": request_hash,
        "digest_version": 1,
        "response_schema_version": 1,
        "response_version": 2,
        "response_snapshot": snapshot(),
        "created_at": NOW,
    }


def test_completed_replay_is_snapshot_based_and_conflicts_fail_closed(
    postgres_engine,
) -> None:
    with postgres_engine.begin() as connection:
        connection.execute(insert(commerce_courier_pickup_idempotency), completed_row())
        repository = PostgresCourierPickupRepository(connection)
        replay = repository.reserve(
            actor_id=ACTOR,
            pickup_id=PICKUP,
            key="postgres-idempotency-0001",
            action=CourierPickupAction.START_TRAVEL,
            request_hash="a" * 64,
            at=NOW,
        )
        assert replay is not None
        assert replay.pickup.version == 2
        with pytest.raises(CourierPickupConflict, match="idempotency_conflict"):
            repository.reserve(
                actor_id=ACTOR,
                pickup_id=PICKUP,
                key="postgres-idempotency-0001",
                action=CourierPickupAction.START_TRAVEL,
                request_hash="b" * 64,
                at=NOW,
            )


def test_legacy_version_fails_closed(postgres_engine) -> None:
    row = completed_row()
    row.update(
        digest_version=0,
        response_schema_version=0,
        response_version=None,
        response_snapshot=None,
    )
    with postgres_engine.begin() as connection:
        connection.execute(insert(commerce_courier_pickup_idempotency), row)
        with pytest.raises(CourierPickupConflict, match="incompatible"):
            PostgresCourierPickupRepository(connection).reserve(
                actor_id=ACTOR,
                pickup_id=PICKUP,
                key="postgres-idempotency-0001",
                action=CourierPickupAction.START_TRAVEL,
                request_hash="a" * 64,
                at=NOW,
            )


@pytest.mark.parametrize(
    "change", [{"digest_version": 2}, {"response_schema_version": 2}]
)
def test_unknown_versions_are_rejected_by_schema(postgres_engine, change) -> None:
    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            insert(commerce_courier_pickup_idempotency),
            {**completed_row(), **change},
        )


def test_malformed_snapshot_and_sensitive_material_are_rejected_or_absent(
    postgres_engine,
) -> None:
    with postgres_engine.begin() as connection:
        connection.execute(insert(commerce_courier_pickup_idempotency), completed_row())
        connection.execute(
            update(commerce_courier_pickup_idempotency).values(
                response_snapshot={"response_schema_version": 1, "token": "forbidden"}
            )
        )
        with pytest.raises(CourierPickupConflict, match="incompatible"):
            PostgresCourierPickupRepository(connection).reserve(
                actor_id=ACTOR,
                pickup_id=PICKUP,
                key="postgres-idempotency-0001",
                action=CourierPickupAction.START_TRAVEL,
                request_hash="a" * 64,
                at=NOW,
            )
        stored = connection.execute(
            select(commerce_courier_pickup_idempotency.c.request_hash)
        ).scalar_one()
        assert stored == "a" * 64
