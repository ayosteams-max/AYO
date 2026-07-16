from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.ride_request.engine import transition, validate_request, zone_contains
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    LocationSource,
    PickupDefinition,
    PickupSafetyStatus,
    RideRequest,
    RideRequestState,
    ServiceZone,
    ValidationPolicy,
    ValidationStatus,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)
POLICY = ValidationPolicy(
    version="ride.validation.v1",
    maximum_accuracy_metres=100,
    maximum_observation_age_seconds=300,
    minimum_separation_metres=50,
    request_ttl_seconds=900,
    effective_from=NOW - timedelta(days=1),
)


def pickup(**changes):
    values = dict(
        coordinate=Coordinate(latitude=9.0, longitude=38.7),
        source=LocationSource.RIDER_SELECTED,
        observed_at=NOW,
        accuracy_metres=20,
        map_confidence_bps=8000,
        policy_version="pickup.v1",
    )
    values.update(changes)
    return PickupDefinition(**values)


def destination(**changes):
    values = dict(
        coordinate=Coordinate(latitude=9.02, longitude=38.72),
        source=LocationSource.RIDER_SELECTED,
        observed_at=NOW,
    )
    values.update(changes)
    return DestinationDefinition(**values)


def zone(**changes):
    values = dict(
        code="zone.synthetic",
        version="zone.v1",
        min_latitude=8.5,
        max_latitude=9.5,
        min_longitude=38.2,
        max_longitude=39.2,
        supported_service_types=frozenset({"immediate_standard"}),
        active_from=NOW - timedelta(days=1),
        policy_version="zone.policy.v1",
    )
    values.update(changes)
    return ServiceZone(**values)


def request(p, d, z):
    return RideRequest(
        client_request_id=uuid4(),
        rider_identity_id=uuid4(),
        pickup_id=p.pickup_id,
        destination_id=d.destination_id,
        service_zone_id=z.zone_id,
        consent_policy_version="consent.v1",
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def test_state_machine_requires_valid_path_and_cancellation_reason() -> None:
    p, d, z = pickup(), destination(), zone()
    item = request(p, d, z)
    validating = transition(item, RideRequestState.VALIDATING, at=NOW)
    assert (
        transition(validating, RideRequestState.READY_FOR_DISPATCH, at=NOW).version == 3
    )
    with pytest.raises(ValueError, match="reason"):
        transition(item, RideRequestState.CANCELLED, at=NOW)
    with pytest.raises(ValueError, match="Invalid"):
        transition(item, RideRequestState.DRAFT, at=NOW)


def test_validation_accepts_only_current_safe_supported_request() -> None:
    p, d, z = pickup(), destination(), zone()
    item = request(p, d, z)
    decision = validate_request(
        request=item,
        pickup=p,
        destination=d,
        zone=z,
        policy=POLICY,
        at=NOW,
        rider_active=True,
        has_conflicting_request=False,
    )
    assert decision.status is ValidationStatus.VALID
    assert decision.zone_version == "zone.v1"


@pytest.mark.parametrize(
    ("p", "d", "z", "reason"),
    [
        (
            pickup(accuracy_metres=500),
            destination(),
            zone(),
            "pickup.accuracy_insufficient",
        ),
        (
            pickup(observed_at=NOW - timedelta(minutes=10)),
            destination(),
            zone(),
            "pickup.observation_stale",
        ),
        (
            pickup(),
            destination(coordinate=Coordinate(latitude=9.00001, longitude=38.70001)),
            zone(),
            "destination.too_close",
        ),
        (
            pickup(safety_status=PickupSafetyStatus.RESTRICTED),
            destination(),
            zone(),
            "pickup.prohibited",
        ),
        (pickup(), destination(), None, "service_zone.unsupported"),
    ],
)
def test_validation_fails_closed(p, d, z, reason) -> None:
    item = request(p, d, z or zone()).model_copy(
        update={"service_zone_id": None if z is None else z.zone_id}
    )
    decision = validate_request(
        request=item,
        pickup=p,
        destination=d,
        zone=z,
        policy=POLICY,
        at=NOW,
        rider_active=True,
        has_conflicting_request=False,
    )
    assert decision.status is ValidationStatus.INVALID
    assert reason in decision.reason_codes


def test_zone_dates_bounds_and_service_injection_fail_closed() -> None:
    assert zone_contains(zone(), Coordinate(latitude=9, longitude=38.7), at=NOW)
    assert not zone_contains(
        zone(active_until=NOW - timedelta(seconds=1)),
        Coordinate(latitude=9, longitude=38.7),
        at=NOW,
    )
    with pytest.raises(ValidationError):
        Coordinate(latitude=91, longitude=0)
    with pytest.raises(ValidationError):
        RideRequest.model_validate(
            request(pickup(), destination(), zone()).model_dump()
            | {"service_type": "airport_premium"}
        )


def test_inactive_validation_policy_fails_closed() -> None:
    p, d, z = pickup(), destination(), zone()
    inactive = POLICY.model_copy(update={"effective_from": NOW + timedelta(days=1)})
    decision = validate_request(
        request=request(p, d, z),
        pickup=p,
        destination=d,
        zone=z,
        policy=inactive,
        at=NOW,
        rider_active=True,
        has_conflicting_request=False,
    )
    assert decision.status is ValidationStatus.INVALID
    assert "policy.inactive" in decision.reason_codes
