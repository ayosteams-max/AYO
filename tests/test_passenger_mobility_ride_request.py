from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.ride_request.engine import transition_mobility_request
from BACKEND.ride_request.models import (
    LuggagePreference,
    MobilityRideRequestState,
    PassengerMobilityRideRequest,
    RideIntentPreferences,
    ScheduleIntentType,
)


def request(**changes) -> PassengerMobilityRideRequest:
    now = datetime.now(UTC)
    values = {
        "client_request_id": uuid4(),
        "requester_subject_id": uuid4(),
        "passenger_subject_id": uuid4(),
        "pickup_reference": "place:addis-bole",
        "destination_reference": "place:addis-piassa",
        "stop_references": ("place:addis-meskel",),
        "schedule_intent": ScheduleIntentType.IMMEDIATE,
        "passenger_count": 2,
        "preferences": RideIntentPreferences(
            accessibility_needs=("mobility.wheelchair",),
            luggage=LuggagePreference.MEDIUM,
            quiet_ride=True,
            child_seat=True,
            child_seat_count=1,
        ),
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(hours=1),
    }
    values.update(changes)
    return PassengerMobilityRideRequest.model_validate(values)


def test_intent_models_immediate_scheduled_stops_preferences_and_accessibility():
    immediate = request()
    assert immediate.schedule_intent is ScheduleIntentType.IMMEDIATE
    assert immediate.stop_references == ("place:addis-meskel",)
    assert immediate.preferences.quiet_ride
    assert immediate.preferences.accessibility_needs == ("mobility.wheelchair",)

    scheduled_at = datetime.now(UTC) + timedelta(days=1)
    scheduled = request(
        schedule_intent=ScheduleIntentType.SCHEDULED, scheduled_for=scheduled_at
    )
    assert scheduled.scheduled_for == scheduled_at

    with pytest.raises(ValidationError):
        request(
            schedule_intent=ScheduleIntentType.IMMEDIATE,
            scheduled_for=scheduled_at,
        )
    with pytest.raises(ValidationError):
        request(destination_reference="place:addis-bole")
    with pytest.raises(ValidationError):
        RideIntentPreferences(child_seat=False, child_seat_count=1)


def test_lifecycle_rejects_invalid_transitions():
    now = datetime.now(UTC)
    draft = request()
    validated = transition_mobility_request(
        draft, MobilityRideRequestState.VALIDATED, at=now
    )
    submitted = transition_mobility_request(
        validated, MobilityRideRequestState.SUBMITTED, at=now
    )
    withdrawn = transition_mobility_request(
        submitted, MobilityRideRequestState.WITHDRAWN, at=now
    )
    assert [draft.version, validated.version, submitted.version, withdrawn.version] == [
        1,
        2,
        3,
        4,
    ]
    with pytest.raises(ValueError, match="Invalid Passenger Mobility"):
        transition_mobility_request(
            withdrawn, MobilityRideRequestState.SUBMITTED, at=now
        )
