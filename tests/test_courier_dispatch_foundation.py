from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.courier_dispatch.engine import (
    CourierDispatchConflict,
    DispatchPolicy,
    target_state,
)
from BACKEND.courier_dispatch.models import (
    CourierDispatchAction,
    CourierDispatchRequest,
    CourierDispatchState,
)
from BACKEND.routes.courier_dispatch import CourierDispatchCommand


def request(
    state: CourierDispatchState = CourierDispatchState.WAITING, version: int = 1
) -> CourierDispatchRequest:
    now = datetime.now(UTC)
    return CourierDispatchRequest(
        dispatch_id=uuid4(),
        order_id=uuid4(),
        merchant_id=uuid4(),
        readiness_message_id=uuid4(),
        state=state,
        version=version,
        policy_code="AYO_COURIER_DISPATCH_POLICY_V1",
        policy_version=1,
        offered_courier_identity_id=None,
        assigned_courier_identity_id=None,
        created_at=now,
        offered_at=None,
        assigned_at=None,
        updated_at=now,
    )


def test_readiness_is_evidence_not_automatic_assignment() -> None:
    value = request()
    assert value.state is CourierDispatchState.WAITING
    assert value.offered_courier_identity_id is None
    assert value.assigned_courier_identity_id is None


def test_only_approved_dispatch_transitions_exist() -> None:
    assert (
        target_state(CourierDispatchState.WAITING, CourierDispatchAction.OFFER)
        is CourierDispatchState.OFFERED
    )
    assert (
        target_state(CourierDispatchState.OFFERED, CourierDispatchAction.ACCEPT)
        is CourierDispatchState.ASSIGNED
    )
    with pytest.raises(CourierDispatchConflict):
        target_state(CourierDispatchState.WAITING, CourierDispatchAction.ACCEPT)
    assert not hasattr(CourierDispatchState, "PICKED_UP")


def test_policy_is_named_and_versioned() -> None:
    assert DispatchPolicy().code == "AYO_COURIER_DISPATCH_POLICY_V1"
    assert DispatchPolicy().version == 1


def test_dispatch_record_rejects_unknown_state() -> None:
    payload = request().model_dump()
    payload["state"] = "courier_arrived"
    with pytest.raises(ValidationError):
        CourierDispatchRequest.model_validate(payload)


def test_courier_dispatch_is_disabled_and_production_fails_closed() -> None:
    assert Settings().COURIER_DISPATCH_PLATFORM_ENABLED is False
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            COURIER_DISPATCH_PLATFORM_ENABLED=True,
        )


def test_mobile_courier_cannot_offer_itself() -> None:
    command = CourierDispatchCommand(
        expected_version=1, action=CourierDispatchAction.OFFER
    )
    with pytest.raises(
        CourierDispatchConflict, match="offer_requires_dispatch_authority"
    ):
        _ = command.courier_action
