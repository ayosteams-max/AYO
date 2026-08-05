from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from queue import Queue
from time import monotonic, sleep
from uuid import UUID

import pytest
from sqlalchemy import delete, event, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.idempotency import CourierPickupReplaySnapshotV1
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupRecord,
    CourierPickupState,
    CourierPickupView,
)
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.courier_pickup_repository import (
    PostgresCourierPickupRepository,
)
from BACKEND.persistence.tables import (
    audit_events,
    commerce_courier_dispatch_requests,
    commerce_courier_pickup_events,
    commerce_courier_pickup_evidence,
    commerce_courier_pickup_idempotency,
    commerce_courier_pickups,
    commerce_order_outbox,
    commerce_orders,
    courier_dispatch_assignments,
    courier_dispatch_offers,
    identities,
    identity_role_assignments,
    merchant_profiles,
    permissions,
    role_permissions,
    roles,
)

pytestmark = pytest.mark.integration

ACTOR = UUID("20000000-0000-4000-8000-000000000001")
PICKUP = UUID("20000000-0000-4000-8000-000000000002")
ASSIGNMENT = UUID("20000000-0000-4000-8000-000000000003")
NOW = datetime(2026, 8, 5, tzinfo=UTC)
ORDER = UUID("20000000-0000-4000-8000-000000000004")
DISPATCH = UUID("20000000-0000-4000-8000-000000000005")
OFFER = UUID("20000000-0000-4000-8000-000000000006")
MERCHANT = UUID("20000000-0000-4000-8000-000000000007")
MERCHANT_OWNER = UUID("20000000-0000-4000-8000-000000000008")
CUSTOMER = UUID("20000000-0000-4000-8000-000000000009")
CORRELATION = UUID("20000000-0000-4000-8000-00000000000a")
CAUSATION = UUID("20000000-0000-4000-8000-00000000000b")
KEY = "postgres-idempotency-contention-0001"
HASH = "c" * 64
ROLE = UUID("20000000-0000-4000-8000-00000000000c")
ROLE_ASSIGNMENT = UUID("20000000-0000-4000-8000-00000000000d")


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


def _seed_command_state(engine) -> None:
    with engine.begin() as connection:
        for identity_id, identity_type in (
            (ACTOR, "driver"),
            (MERCHANT_OWNER, "merchant"),
            (CUSTOMER, "rider"),
        ):
            connection.execute(
                insert(identities).values(
                    identity_id=identity_id,
                    public_id=identity_id,
                    identity_type=identity_type,
                    status="active",
                    created_at=NOW,
                    updated_at=NOW,
                    version=1,
                )
            )
        connection.execute(
            insert(merchant_profiles).values(
                merchant_id=MERCHANT,
                owner_identity_id=MERCHANT_OWNER,
                legal_name="Synthetic Merchant",
                display_name="Synthetic Merchant",
                kind="restaurant",
                onboarding_source="self_service",
                state="approved",
                capability_code="eat.order.accept",
                market_code="ET-AA",
                version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            insert(commerce_orders).values(
                order_id=ORDER,
                customer_identity_id=CUSTOMER,
                merchant_id=MERCHANT,
                merchant_display_name="Synthetic Merchant",
                merchant_version=1,
                state="ready_for_courier",
                version=1,
                pricing_evidence={},
                evidence_hash="d" * 64,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(commerce_courier_dispatch_requests).values(
                dispatch_id=DISPATCH,
                order_id=ORDER,
                merchant_id=MERCHANT,
                readiness_message_id=UUID(int=31),
                state="assigned",
                version=1,
                policy_code="AYO_COURIER_DISPATCH_POLICY_V1",
                policy_version=1,
                attempt_number=1,
                active_assignment_id=ASSIGNMENT,
                assigned_courier_identity_id=ACTOR,
                created_at=NOW,
                assigned_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            insert(courier_dispatch_offers).values(
                offer_id=OFFER,
                dispatch_id=DISPATCH,
                attempt_number=1,
                courier_identity_id=ACTOR,
                state="accepted",
                offered_at=NOW,
                expires_at=NOW.replace(hour=1),
                resolved_at=NOW,
                resolution_actor_identity_id=ACTOR,
                resolution_reason="accepted",
                version=1,
            )
        )
        connection.execute(
            insert(courier_dispatch_assignments).values(
                assignment_id=ASSIGNMENT,
                dispatch_id=DISPATCH,
                offer_id=OFFER,
                attempt_number=1,
                courier_identity_id=ACTOR,
                state="assigned",
                assigned_at=NOW,
                version=1,
            )
        )
        connection.execute(
            insert(commerce_courier_pickups).values(
                pickup_id=PICKUP,
                dispatch_id=DISPATCH,
                order_id=ORDER,
                merchant_id=MERCHANT,
                assigned_courier_identity_id=ACTOR,
                assignment_id=ASSIGNMENT,
                assignment_version=1,
                attempt_number=1,
                assignment_message_id=UUID(int=32),
                policy_code="AYO_COURIER_PICKUP_POLICY_V1",
                policy_version=1,
                state=CourierPickupState.ASSIGNED.value,
                version=1,
                assigned_at=NOW,
                updated_at=NOW,
            )
        )
        permission_id = connection.execute(
            select(permissions.c.permission_id).where(
                permissions.c.code == "courier_pickup.manage_assigned"
            )
        ).scalar_one()
        connection.execute(
            insert(roles).values(
                role_id=ROLE,
                code="courier_pickup_idempotency_test",
                description="Synthetic Courier Pickup idempotency test role",
                system_managed=False,
                created_at=NOW,
                version=1,
            )
        )
        connection.execute(
            insert(role_permissions).values(
                role_id=ROLE,
                permission_id=permission_id,
                granted_at=NOW,
            )
        )
        connection.execute(
            insert(identity_role_assignments).values(
                assignment_id=ROLE_ASSIGNMENT,
                identity_id=ACTOR,
                role_id=ROLE,
                assigned_by_identity_id=ACTOR,
                assigned_at=NOW,
            )
        )


def _cleanup_command_state(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            delete(identity_role_assignments).where(
                identity_role_assignments.c.assignment_id == ROLE_ASSIGNMENT
            )
        )
        connection.execute(
            delete(role_permissions).where(role_permissions.c.role_id == ROLE)
        )
        connection.execute(delete(roles).where(roles.c.role_id == ROLE))
        connection.execute(
            delete(audit_events).where(
                audit_events.c.resource_type == "courier_pickup",
                audit_events.c.resource_id == str(PICKUP),
            )
        )
        connection.execute(
            delete(commerce_order_outbox).where(
                commerce_order_outbox.c.order_id == ORDER
            )
        )
        connection.execute(
            delete(commerce_courier_pickup_evidence).where(
                commerce_courier_pickup_evidence.c.pickup_id == PICKUP
            )
        )
        connection.execute(
            delete(commerce_courier_pickup_events).where(
                commerce_courier_pickup_events.c.pickup_id == PICKUP
            )
        )
        connection.execute(
            delete(commerce_courier_pickup_idempotency).where(
                commerce_courier_pickup_idempotency.c.pickup_id == PICKUP
            )
        )
        connection.execute(
            delete(commerce_courier_pickups).where(
                commerce_courier_pickups.c.pickup_id == PICKUP
            )
        )
        connection.execute(
            delete(courier_dispatch_assignments).where(
                courier_dispatch_assignments.c.assignment_id == ASSIGNMENT
            )
        )
        connection.execute(
            delete(courier_dispatch_offers).where(
                courier_dispatch_offers.c.offer_id == OFFER
            )
        )
        connection.execute(
            delete(commerce_courier_dispatch_requests).where(
                commerce_courier_dispatch_requests.c.dispatch_id == DISPATCH
            )
        )
        connection.execute(
            delete(commerce_orders).where(commerce_orders.c.order_id == ORDER)
        )
        connection.execute(
            delete(merchant_profiles).where(merchant_profiles.c.merchant_id == MERCHANT)
        )
        connection.execute(
            delete(identities).where(
                identities.c.identity_id.in_((ACTOR, MERCHANT_OWNER, CUSTOMER))
            )
        )


@pytest.fixture
def command_state(postgres_engine):
    _cleanup_command_state(postgres_engine)
    _seed_command_state(postgres_engine)
    yield
    _cleanup_command_state(postgres_engine)


def _subject() -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=ACTOR,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )


def _execute_on_connection(
    connection,
    *,
    request_hash: str = HASH,
    key: str = KEY,
    failure_stage: str | None = None,
) -> CourierPickupView:
    stage_patterns = {
        "after_reservation": (
            "after",
            "INSERT INTO ayo.commerce_courier_pickup_idempotency",
        ),
        "after_aggregate": ("after", "UPDATE ayo.commerce_courier_pickups"),
        "after_event": ("after", "INSERT INTO ayo.commerce_courier_pickup_events"),
        "after_evidence": ("after", "INSERT INTO ayo.commerce_courier_pickup_evidence"),
        "before_outbox": ("before", "INSERT INTO ayo.commerce_order_outbox"),
        "before_snapshot": ("before", "UPDATE ayo.commerce_courier_pickup_idempotency"),
        "after_audit": ("after", "INSERT INTO ayo.audit_events"),
    }
    if failure_stage in stage_patterns:
        timing, pattern = stage_patterns[failure_stage]

        def inject(_conn, _cursor, statement, _parameters, _context, _many):
            if pattern in statement:
                raise RuntimeError(f"injected_{failure_stage}")

        event.listen(connection, f"{timing}_cursor_execute", inject)
    repository = PostgresCourierPickupRepository(connection)
    current = repository.get(PICKUP, lock=True)
    assert current is not None
    replay = repository.reserve(
        actor_id=ACTOR,
        pickup_id=PICKUP,
        key=key,
        action=CourierPickupAction.START_TRAVEL,
        request_hash=request_hash,
        at=NOW,
    )
    if replay is not None:
        return replay
    result = repository.transition(
        current,
        target=CourierPickupState.TRAVELLING,
        action=CourierPickupAction.START_TRAVEL,
        actor_id=ACTOR,
        key=key,
        at=NOW,
        authority_basis="courier_pickup.manage_assigned",
        correlation_id=CORRELATION,
        causation_id=CAUSATION,
    )
    PostgresAuditEventRepository(connection).append(
        CourierPickupApplication._audit(
            _subject(),
            result,
            CourierPickupAction.START_TRAVEL,
            CORRELATION,
            CAUSATION,
            key,
        )
    )
    if failure_stage in {"before_commit", "after_audit"}:
        raise RuntimeError(f"injected_{failure_stage}")
    return result


def _execute(engine, **kwargs) -> CourierPickupView:
    with engine.begin() as connection:
        return _execute_on_connection(connection, **kwargs)


def _effect_counts(engine) -> tuple[int, int, int, int, int]:
    with engine.connect() as connection:
        return (
            connection.execute(
                select(func.count()).select_from(commerce_courier_pickup_idempotency)
            ).scalar_one(),
            connection.execute(
                select(func.count()).select_from(commerce_courier_pickup_events)
            ).scalar_one(),
            connection.execute(
                select(func.count()).select_from(commerce_courier_pickup_evidence)
            ).scalar_one(),
            connection.execute(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.resource_id == str(PICKUP))
            ).scalar_one(),
            connection.execute(
                select(func.count())
                .select_from(commerce_order_outbox)
                .where(
                    commerce_order_outbox.c.order_id == ORDER,
                    commerce_order_outbox.c.event_type
                    == "commerce.courier_pickup.travel_started",
                )
            ).scalar_one(),
        )


def _wait_for_real_lock(engine, backend_pid: int) -> None:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with engine.connect() as connection:
            waiting = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE pid=:pid AND wait_event_type='Lock'"
                ),
                {"pid": backend_pid},
            ).scalar_one()
        if waiting:
            return
        sleep(0.02)
    pytest.fail("contender never entered a real PostgreSQL lock wait")


@pytest.mark.parametrize("conflicting", [False, True])
def test_real_postgresql_contention_executes_once(
    postgres_engine, command_state, conflicting
) -> None:
    del command_state
    contender_pid: Queue[int] = Queue(maxsize=1)

    def contend():
        with postgres_engine.begin() as connection:
            contender_pid.put(
                connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
            )
            return _execute_on_connection(
                connection, request_hash="e" * 64 if conflicting else HASH
            )

    first_connection = postgres_engine.connect()
    transaction = first_connection.begin()
    try:
        repository = PostgresCourierPickupRepository(first_connection)
        assert repository.get(PICKUP, lock=True) is not None
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(contend)
            _wait_for_real_lock(postgres_engine, contender_pid.get(timeout=5))
            first = _execute_on_connection(first_connection)
            transaction.commit()
            if conflicting:
                with pytest.raises(CourierPickupConflict, match="idempotency_conflict"):
                    future.result(timeout=10)
            else:
                assert future.result(timeout=10) == first
    finally:
        if transaction.is_active:
            transaction.rollback()
        first_connection.close()
    assert _effect_counts(postgres_engine) == (1, 1, 1, 1, 1)


@pytest.mark.parametrize(
    "failure_stage",
    [
        "after_reservation",
        "after_aggregate",
        "after_event",
        "after_evidence",
        "before_outbox",
        "before_snapshot",
        "after_audit",
        "before_commit",
    ],
)
def test_forced_failure_rolls_back_every_effect(
    postgres_engine, command_state, failure_stage
) -> None:
    del command_state
    with pytest.raises(RuntimeError, match=f"injected_{failure_stage}"):
        _execute(postgres_engine, failure_stage=failure_stage)
    assert _effect_counts(postgres_engine) == (0, 0, 0, 0, 0)
    with postgres_engine.connect() as connection:
        row = connection.execute(
            select(
                commerce_courier_pickups.c.state, commerce_courier_pickups.c.version
            ).where(commerce_courier_pickups.c.pickup_id == PICKUP)
        ).one()
    assert row == (CourierPickupState.ASSIGNED.value, 1)


def test_database_lock_timeout_before_commit_retries_once(
    postgres_engine, command_state
) -> None:
    del command_state
    blocker = postgres_engine.connect()
    transaction = blocker.begin()
    try:
        PostgresCourierPickupRepository(blocker).get(PICKUP, lock=True)
        with pytest.raises(DBAPIError), postgres_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout='100ms'"))
            _execute_on_connection(connection)
    finally:
        transaction.rollback()
        blocker.close()
    assert _effect_counts(postgres_engine) == (0, 0, 0, 0, 0)
    assert _execute(postgres_engine).pickup.version == 2
    assert _effect_counts(postgres_engine) == (1, 1, 1, 1, 1)


def test_post_commit_uncertainty_and_restart_replay_are_snapshot_only(
    postgres_engine, command_state
) -> None:
    del command_state
    committed = _execute(postgres_engine)
    with pytest.raises(ConnectionError, match="client lost acknowledgement"):
        raise ConnectionError("client lost acknowledgement")
    restarted = PostgresCourierPickupRepository
    with postgres_engine.begin() as connection:
        connection.execute(
            update(commerce_courier_pickups)
            .where(commerce_courier_pickups.c.pickup_id == PICKUP)
            .values(version=3, state=CourierPickupState.ARRIVED.value)
        )
    with postgres_engine.begin() as connection:
        replay = restarted(connection).reserve(
            actor_id=ACTOR,
            pickup_id=PICKUP,
            key=KEY,
            action=CourierPickupAction.START_TRAVEL,
            request_hash=HASH,
            at=NOW.replace(year=2027),
        )
    assert replay == committed
    assert replay is not None and replay.pickup.version == 2
    assert _effect_counts(postgres_engine) == (1, 1, 1, 1, 1)
    with (
        postgres_engine.begin() as connection,
        pytest.raises(CourierPickupConflict, match="idempotency_conflict"),
    ):
        restarted(connection).reserve(
            actor_id=ACTOR,
            pickup_id=PICKUP,
            key=KEY,
            action=CourierPickupAction.START_TRAVEL,
            request_hash="f" * 64,
            at=NOW,
        )
    assert _effect_counts(postgres_engine) == (1, 1, 1, 1, 1)


def test_application_replay_returns_persisted_snapshot_after_revalidation(
    postgres_engine, postgres_composition, command_state
) -> None:
    del command_state
    first = CourierPickupApplication(postgres_composition).courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key=KEY,
        at=NOW,
    )
    assert _effect_counts(postgres_engine) == (1, 1, 1, 1, 1)

    with postgres_engine.begin() as connection:
        connection.execute(
            update(identity_role_assignments)
            .where(identity_role_assignments.c.assignment_id == ROLE_ASSIGNMENT)
            .values(
                revoked_at=NOW, revoked_by_identity_id=ACTOR, revocation_reason="test"
            )
        )
    with pytest.raises(CourierPickupConflict, match="access_denied"):
        CourierPickupApplication(postgres_composition).courier_command(
            _subject(),
            pickup_id=PICKUP,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key=KEY,
            at=NOW.replace(year=2027),
        )

    with postgres_engine.begin() as connection:
        connection.execute(
            update(identity_role_assignments)
            .where(identity_role_assignments.c.assignment_id == ROLE_ASSIGNMENT)
            .values(
                revoked_at=None,
                revoked_by_identity_id=None,
                revocation_reason=None,
            )
        )
        connection.execute(
            update(commerce_courier_pickups)
            .where(commerce_courier_pickups.c.pickup_id == PICKUP)
            .values(version=3, state=CourierPickupState.ARRIVED.value)
        )

    fresh_composition = type(postgres_composition)(postgres_engine)
    replay = CourierPickupApplication(fresh_composition).courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key=KEY,
        at=NOW.replace(year=2027),
    )
    assert replay == first
    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert _effect_counts(postgres_engine) == (1, 1, 1, 1, 1)


def test_v1_snapshot_database_size_bound_is_fail_closed(postgres_engine) -> None:
    row = completed_row()
    row["response_snapshot"] = {"payload": "x" * 65_537}
    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(insert(commerce_courier_pickup_idempotency), row)
