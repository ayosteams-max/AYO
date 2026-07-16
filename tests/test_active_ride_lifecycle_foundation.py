from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.active_ride.engine import ActiveRideConflict, transition
from BACKEND.active_ride.lifecycle import LifecycleCommand, LifecycleCommandType
from BACKEND.active_ride.models import ActiveRide, ActiveRideState

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def ride(state: ActiveRideState) -> ActiveRide:
    return ActiveRide(
        rider_id=uuid4(),
        driver_id=uuid4(),
        vehicle_id=uuid4(),
        assignment_id=uuid4(),
        ride_request_id=uuid4(),
        dispatch_handoff_id=uuid4(),
        source_assignment_version=2,
        state=state,
        pickup_place_id="pickup.reference",
        destination_place_id="destination.reference",
        service_type="immediate_standard",
        created_at=NOW,
        updated_at=NOW,
        last_sequence=1,
    )


def test_canonical_happy_path_is_typed_and_deterministic() -> None:
    current = ride(ActiveRideState.DRIVER_ASSIGNED)
    for target in (
        ActiveRideState.DRIVER_EN_ROUTE,
        ActiveRideState.DRIVER_ARRIVED,
        ActiveRideState.PICKUP_CONFIRMED,
        ActiveRideState.RIDE_IN_PROGRESS,
        ActiveRideState.DESTINATION_ARRIVED,
        ActiveRideState.COMPLETED,
    ):
        current = transition(current, target, now=NOW)
    assert current.state is ActiveRideState.COMPLETED
    assert current.version == 7
    assert current.last_sequence == 7


@pytest.mark.parametrize(
    "target",
    [
        ActiveRideState.DRIVER_CANCELLED,
        ActiveRideState.RIDER_CANCELLED,
        ActiveRideState.SUPPORT_INTERRUPTED,
        ActiveRideState.SYSTEM_INTERRUPTED,
    ],
)
def test_interruption_states_are_explicit(target: ActiveRideState) -> None:
    changed = transition(ride(ActiveRideState.DRIVER_ASSIGNED), target, now=NOW)
    assert changed.state is target
    with pytest.raises(ActiveRideConflict, match="unsupported_transition"):
        transition(changed, ActiveRideState.COMPLETED, now=NOW)


def test_invalid_lifecycle_jump_and_unbounded_evidence_fail_closed() -> None:
    with pytest.raises(ActiveRideConflict, match="unsupported_transition"):
        transition(
            ride(ActiveRideState.DRIVER_ASSIGNED),
            ActiveRideState.COMPLETED,
            now=NOW,
        )
    with pytest.raises(ValidationError):
        LifecycleCommand(
            command_id=uuid4(),
            expected_version=1,
            command_type=LifecycleCommandType.DRIVER_EN_ROUTE,
            reason_code="driver_started",
            evidence_references=tuple(str(uuid4()) for _ in range(11)),
        )
