from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.courier_pickup.engine import (
    CourierPickupConflict,
    CourierPickupPolicy,
    target_state,
)
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupExceptionReason,
    CourierPickupRecord,
    CourierPickupState,
)


def record(
    state: CourierPickupState = CourierPickupState.ASSIGNED,
) -> CourierPickupRecord:
    now = datetime.now(UTC)
    return CourierPickupRecord(
        pickup_id=uuid4(),
        dispatch_id=uuid4(),
        assignment_id=uuid4(),
        assignment_version=1,
        attempt_number=1,
        order_id=uuid4(),
        merchant_id=uuid4(),
        assigned_courier_identity_id=uuid4(),
        assignment_message_id=uuid4(),
        policy_code="AYO_COURIER_PICKUP_POLICY_V1",
        policy_version=1,
        state=state,
        version=1,
        assigned_at=now,
        travelling_at=None,
        arrived_at=None,
        merchant_acknowledged_at=None,
        waiting_duration_seconds=None,
        terminal_reason=None,
        custody_accepted_at=None,
        updated_at=now,
    )


def test_assignment_is_not_arrival_or_pickup() -> None:
    value = record()
    assert value.state is CourierPickupState.ASSIGNED
    assert value.arrived_at is None
    assert value.merchant_acknowledged_at is None
    assert not hasattr(CourierPickupState, "PICKED_UP")


def test_only_approved_transitions_exist() -> None:
    assert (
        target_state(CourierPickupState.ASSIGNED, CourierPickupAction.START_TRAVEL)
        is CourierPickupState.TRAVELLING
    )
    assert (
        target_state(CourierPickupState.TRAVELLING, CourierPickupAction.MARK_ARRIVED)
        is CourierPickupState.ARRIVED
    )
    assert (
        target_state(
            CourierPickupState.ARRIVED, CourierPickupAction.ACKNOWLEDGE_ARRIVAL
        )
        is CourierPickupState.WAITING
    )
    with pytest.raises(CourierPickupConflict):
        target_state(CourierPickupState.ASSIGNED, CourierPickupAction.MARK_ARRIVED)


def test_append_only_corrections_use_governed_reverse_projection() -> None:
    assert (
        target_state(CourierPickupState.ARRIVED, CourierPickupAction.CORRECT_ARRIVAL)
        is CourierPickupState.TRAVELLING
    )
    assert (
        target_state(CourierPickupState.WAITING, CourierPickupAction.CORRECT_WAITING)
        is CourierPickupState.ARRIVED
    )
    with pytest.raises(CourierPickupConflict):
        target_state(CourierPickupState.ASSIGNED, CourierPickupAction.CORRECT_ARRIVAL)


def test_attempt_can_only_end_in_truthful_pre_custody_terminal_state() -> None:
    for state in (
        CourierPickupState.ASSIGNED,
        CourierPickupState.TRAVELLING,
        CourierPickupState.ARRIVED,
        CourierPickupState.WAITING,
    ):
        assert (
            target_state(state, CourierPickupAction.END_ATTEMPT)
            is CourierPickupState.ENDED_BEFORE_CUSTODY
        )
    with pytest.raises(CourierPickupConflict):
        target_state(
            CourierPickupState.ENDED_BEFORE_CUSTODY,
            CourierPickupAction.END_ATTEMPT,
        )


def test_exception_taxonomy_is_closed_and_version_one_policy_is_explicit() -> None:
    assert {reason.value for reason in CourierPickupExceptionReason} == {
        "assignment_closed_or_revoked",
        "merchant_location_unreachable",
        "merchant_not_found",
        "merchant_unavailable",
        "order_not_ready",
        "readiness_corrected",
        "courier_unable_to_continue",
        "authority_or_identity_failure",
        "duplicate_or_invalid_attempt",
        "other_review_required",
    }
    assert record().policy_code == "AYO_COURIER_PICKUP_POLICY_V1"


def test_location_evidence_is_optional_but_fresh_when_supplied() -> None:
    policy = CourierPickupPolicy()
    now = datetime.now(UTC)
    policy.validate_location_evidence(
        observed_at=now - timedelta(minutes=4), evaluated_at=now
    )
    with pytest.raises(CourierPickupConflict, match="location_evidence_stale"):
        policy.validate_location_evidence(
            observed_at=now - timedelta(minutes=6), evaluated_at=now
        )


def test_unknown_future_state_rejected() -> None:
    payload = record().model_dump()
    payload["state"] = "pickup_verified"
    with pytest.raises(ValidationError):
        CourierPickupRecord.model_validate(payload)


def test_disabled_and_production_fails_closed() -> None:
    assert Settings().COURIER_PICKUP_PLATFORM_ENABLED is False
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION, COURIER_PICKUP_PLATFORM_ENABLED=True
        )
