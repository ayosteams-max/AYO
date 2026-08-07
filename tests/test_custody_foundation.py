from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.courier_dispatch.models import CourierAssignmentState, CourierDispatchState
from BACKEND.courier_pickup.models import CourierPickupState
from BACKEND.custody.application import CustodyApplication
from BACKEND.custody.engine import CustodyConflict, target_state
from BACKEND.custody.models import (
    CustodyAction,
    CustodyRecord,
    CustodyState,
    VerificationMethod,
)
from BACKEND.identity.models import IdentityType


def record(state=CustodyState.WAITING):
    return CustodyRecord(
        custody_id=uuid4(),
        pickup_id=uuid4(),
        order_id=uuid4(),
        merchant_id=uuid4(),
        courier_identity_id=uuid4(),
        state=state,
        version=1,
        sealed_at=None,
        verified_at=None,
        verification_method=None,
        merchant_released_at=None,
        custody_accepted_at=None,
        updated_at=datetime.now(UTC),
    )


def test_independent_custody_transitions():
    assert target_state(CustodyState.WAITING, CustodyAction.SEAL) is CustodyState.SEALED
    assert (
        target_state(CustodyState.SEALED, CustodyAction.VERIFY) is CustodyState.VERIFIED
    )
    assert (
        target_state(CustodyState.VERIFIED, CustodyAction.RELEASE)
        is CustodyState.RELEASED
    )
    assert (
        target_state(CustodyState.RELEASED, CustodyAction.ACCEPT)
        is CustodyState.ACCEPTED
    )
    with pytest.raises(CustodyConflict):
        target_state(CustodyState.VERIFIED, CustodyAction.ACCEPT)


def test_code_hash_is_keyed_and_deterministic():
    one = CustodyApplication(object(), verification_pepper=b"a" * 32)
    two = CustodyApplication(object(), verification_pepper=b"b" * 32)
    assert one._digest("opaque-code") == one._digest("opaque-code")
    assert one._digest("opaque-code") != two._digest("opaque-code")
    assert one._digest("opaque-code") != "opaque-code"


def test_future_delivery_state_absent():
    payload = record().model_dump()
    payload["state"] = "delivered"
    with pytest.raises(ValidationError):
        CustodyRecord.model_validate(payload)


def test_replay_wrong_order_and_concurrency_guards_are_persistent():
    root = Path(__file__).parents[1]
    repository = (root / "BACKEND/persistence/custody_repository.py").read_text()
    migration = (
        root / "database/migrations/versions/20260721_0039_pickup_chain_of_custody.py"
    ).read_text()
    application = (root / "BACKEND/custody/application.py").read_text()
    assert "used_at.is_(None)" in repository
    assert "expires_at >= at" in repository
    assert "commerce_custody_records.c.version == current.version" in repository
    assert "unique=True" in migration
    assert "courier_identity_id != subject.identity_id" in application


def test_short_pepper_and_production_activation_fail_closed():
    with pytest.raises(ValueError):
        CustodyApplication(object(), verification_pepper=b"short")
    assert Settings().CUSTODY_PLATFORM_ENABLED is False
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, CUSTODY_PLATFORM_ENABLED=True)


@pytest.mark.parametrize(
    "action,state",
    [
        (CustodyAction.VERIFY, CustodyState.SEALED),
        (CustodyAction.ACCEPT, CustodyState.RELEASED),
    ],
)
@pytest.mark.parametrize(
    "dispatch_state,assignment_state,assignment_version",
    [
        (
            CourierDispatchState.WAITING,
            CourierAssignmentState.RELEASED,
            2,
        ),
        (CourierDispatchState.ASSIGNED, CourierAssignmentState.ASSIGNED, 2),
    ],
)
def test_courier_custody_commands_recheck_assignment_before_reservation(
    action, state, dispatch_state, assignment_state, assignment_version
):
    current = record(state)
    dispatch_id = uuid4()
    assignment_id = uuid4()
    pickup = SimpleNamespace(
        pickup_id=current.pickup_id,
        order_id=current.order_id,
        merchant_id=current.merchant_id,
        dispatch_id=dispatch_id,
        assignment_id=assignment_id,
        assignment_version=1,
        assigned_courier_identity_id=current.courier_identity_id,
        state=CourierPickupState.WAITING,
    )
    calls = {"reserve": 0, "verify": 0, "transition": 0}
    custody = SimpleNamespace(
        get=lambda *args, **kwargs: current,
        reserve=lambda **kwargs: calls.__setitem__("reserve", calls["reserve"] + 1),
        verify=lambda *args, **kwargs: calls.__setitem__("verify", calls["verify"] + 1),
        transition=lambda *args, **kwargs: calls.__setitem__(
            "transition", calls["transition"] + 1
        ),
    )
    dispatch = SimpleNamespace(
        dispatch_id=dispatch_id,
        order_id=current.order_id,
        merchant_id=current.merchant_id,
        state=dispatch_state,
        active_assignment_id=(
            assignment_id if dispatch_state is CourierDispatchState.ASSIGNED else None
        ),
        assigned_courier_identity_id=(
            current.courier_identity_id
            if dispatch_state is CourierDispatchState.ASSIGNED
            else None
        ),
    )
    assignment = SimpleNamespace(
        dispatch_id=dispatch_id,
        courier_identity_id=current.courier_identity_id,
        state=assignment_state,
        version=assignment_version,
    )
    unit = SimpleNamespace(
        custody=custody,
        courier_pickup=SimpleNamespace(get=lambda *args, **kwargs: pickup),
        courier_dispatch=SimpleNamespace(
            get=lambda *args, **kwargs: dispatch,
            get_assignment=lambda *args, **kwargs: assignment,
        ),
    )
    unit.__enter__ = lambda: unit
    unit.__exit__ = lambda *args: False

    class UnitContext:
        def __enter__(self):
            return unit

        def __exit__(self, *args):
            return False

    application = CustodyApplication(
        SimpleNamespace(unit_of_work=lambda: UnitContext()),
        verification_pepper=b"assignment-authority-pepper-value",
    )
    actor = AuthorizationSubject(
        identity_id=current.courier_identity_id,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )

    for _ in range(2):
        with pytest.raises(CustodyConflict, match="^custody_not_found$"):
            application.command(
                actor,
                custody_id=current.custody_id,
                expected_version=current.version,
                action=action,
                idempotency_key="obsolete-custody-assignment-0001",
                at=datetime.now(UTC),
                code="challenge" if action is CustodyAction.VERIFY else None,
                method=(
                    VerificationMethod.QR if action is CustodyAction.VERIFY else None
                ),
            )

    assert calls == {"reserve": 0, "verify": 0, "transition": 0}
    assert current.state is state
    assert current.version == 1
