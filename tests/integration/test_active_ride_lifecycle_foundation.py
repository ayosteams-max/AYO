from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.active_ride.engine import ActiveRideConflict
from BACKEND.active_ride.lifecycle import (
    ActiveRideLifecycleApplication,
    LifecycleCommand,
    LifecycleCommandType,
)
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.tables import active_ride_events, active_rides, dispatch_outbox
from tests.integration.test_dispatch_handoff_localization import (
    eligible_driver,
    ready_request,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, tzinfo=UTC)


def subject(identity_id: UUID, identity_type: IdentityType) -> AuthorizationSubject:
    actor = {
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.DRIVER: ActorType.DRIVER,
        IdentityType.SERVICE: ActorType.SERVICE,
        IdentityType.STAFF: ActorType.STAFF,
    }[identity_type]
    return AuthorizationSubject(
        identity_id=identity_id, identity_type=identity_type, actor_type=actor
    )


def assigned(composition):
    request, rider = ready_request(composition)
    driver = eligible_driver(composition, 10)
    dispatch = ImmediateHandoffService(composition, policy_version="dispatch.v1")
    handoff = dispatch.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key=f"handoff-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = dispatch.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer is not None
    assignment_id = dispatch.respond(
        offer_id=offer.offer_id,
        driver_id=driver.driver_id,
        expected_version=1,
        accept=True,
        idempotency_key=f"accept-{uuid4()}",
        at=NOW,
    )
    assert assignment_id is not None
    return assignment_id, rider, subject(driver.driver_id, IdentityType.DRIVER)


def command(kind: LifecycleCommandType, version: int, *, command_id=None):
    return LifecycleCommand(
        command_id=command_id or uuid4(),
        expected_version=version,
        command_type=kind,
        reason_code=f"test.{kind.value}",
    )


def test_assignment_handoff_full_lifecycle_timeline_and_reconnect(
    postgres_composition,
) -> None:
    assignment_id, rider, driver = assigned(postgres_composition)
    app = ActiveRideLifecycleApplication(postgres_composition.unit_of_work)
    ride = app.start_from_assignment(assignment_id, now=NOW)
    assert app.start_from_assignment(assignment_id, now=NOW).ride_id == ride.ride_id
    service = subject(uuid4(), IdentityType.SERVICE)
    sequence = (
        (driver, LifecycleCommandType.DRIVER_EN_ROUTE),
        (driver, LifecycleCommandType.DRIVER_ARRIVED),
        (service, LifecycleCommandType.PICKUP_CONFIRMED),
        (driver, LifecycleCommandType.RIDE_STARTED),
        (driver, LifecycleCommandType.DESTINATION_ARRIVED),
        (driver, LifecycleCommandType.RIDE_COMPLETED),
    )
    version = 1
    for actor, kind in sequence:
        result = app.command(actor, ride.ride_id, command(kind, version), now=NOW)
        version = result["aggregate_version"]
        assert result["message"]["translation_key"].startswith("active_ride.")
    recovered = ActiveRideLifecycleApplication(
        postgres_composition.unit_of_work
    ).recover(rider, ride.ride_id, after_sequence=2)
    assert recovered["state"] == "completed"
    assert recovered["last_sequence"] == 7
    assert len(recovered["events"]) == 5
    with postgres_composition.unit_of_work() as unit:
        payloads = unit.connection.execute(
            select(dispatch_outbox.c.payload).where(
                dispatch_outbox.c.aggregate_id == ride.ride_id
            )
        ).scalars()
        assert all(
            "translation_key" not in str(item) or "active_ride." in str(item)
            for item in payloads
        )


def test_ownership_authority_idempotency_and_changed_replay(
    postgres_composition,
) -> None:
    assignment_id, rider, driver = assigned(postgres_composition)
    app = ActiveRideLifecycleApplication(postgres_composition.unit_of_work)
    ride = app.start_from_assignment(assignment_id, now=NOW)
    command_id = uuid4()
    item = command(LifecycleCommandType.DRIVER_EN_ROUTE, 1, command_id=command_id)
    first = app.command(driver, ride.ride_id, item, now=NOW)
    duplicate = app.command(driver, ride.ride_id, item, now=NOW)
    assert first["aggregate_version"] == duplicate["aggregate_version"] == 2
    assert duplicate["command_created"] is False
    with pytest.raises(ActiveRideConflict, match="idempotency_conflict"):
        app.command(
            driver,
            ride.ride_id,
            command(LifecycleCommandType.DRIVER_ARRIVED, 2, command_id=command_id),
            now=NOW,
        )
    with pytest.raises(ActiveRideConflict, match="access_denied"):
        app.command(
            rider,
            ride.ride_id,
            command(LifecycleCommandType.RIDE_COMPLETED, 2),
            now=NOW,
        )
    with pytest.raises(ActiveRideConflict, match="ride_not_found"):
        app.recover(
            subject(uuid4(), IdentityType.RIDER), ride.ride_id, after_sequence=0
        )


def test_concurrent_commands_have_one_winner_and_atomic_outbox(
    postgres_composition,
) -> None:
    assignment_id, _, driver = assigned(postgres_composition)
    app = ActiveRideLifecycleApplication(postgres_composition.unit_of_work)
    ride = app.start_from_assignment(assignment_id, now=NOW)

    def submit():
        try:
            return app.command(
                driver,
                ride.ride_id,
                command(LifecycleCommandType.DRIVER_EN_ROUTE, 1),
                now=NOW,
            )["aggregate_version"]
        except ActiveRideConflict:
            return "lost"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: submit(), range(2)))
    assert outcomes.count(2) == 1 and outcomes.count("lost") == 1
    with postgres_composition.unit_of_work() as unit:
        event_count = unit.connection.execute(
            select(func.count())
            .select_from(active_ride_events)
            .where(active_ride_events.c.ride_id == ride.ride_id)
        ).scalar_one()
        outbox_count = unit.connection.execute(
            select(func.count())
            .select_from(dispatch_outbox)
            .where(dispatch_outbox.c.aggregate_id == ride.ride_id)
        ).scalar_one()
    assert event_count == outbox_count == 2


def test_transaction_rollback_does_not_leave_partial_ride(postgres_composition) -> None:
    assignment_id, _, _ = assigned(postgres_composition)
    with (
        pytest.raises(RuntimeError, match="rollback"),
        postgres_composition.unit_of_work() as unit,
    ):
        ride = unit.active_rides.create_from_immediate_assignment(
            assignment_id=assignment_id,
            lifecycle_policy_version="active_ride.v1",
            now=NOW,
        )
        assert ride.state.value == "driver_assigned"
        raise RuntimeError("rollback")
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(active_rides)
            ).scalar_one()
            == 0
        )
