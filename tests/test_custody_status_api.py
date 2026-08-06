from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_dispatch.models import (
    CourierAssignmentState,
    CourierDispatchState,
)
from BACKEND.custody.application import CustodyApplication
from BACKEND.custody.engine import CustodyConflict
from BACKEND.custody.models import (
    CustodyRecord,
    CustodyState,
    CustodyStatusSnapshot,
    PickupChallenge,
)
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import MerchantState
from BACKEND.routes.custody import (
    CourierCustodyRequiredAction,
    CourierCustodyStatus,
    CustodyRecoveryCategory,
    CustodyWaitingFor,
    MerchantCustodyRequiredAction,
    MerchantCustodyStatus,
    _courier_status,
    _merchant_status,
    _status_call,
    create_custody_router,
)

NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)
PICKUP = uuid4()
ORDER = uuid4()
MERCHANT = uuid4()
COURIER = uuid4()
CUSTODY = uuid4()
DISPATCH = uuid4()
ASSIGNMENT = uuid4()

COMMON_FIELDS = {
    "custody_id",
    "order_id",
    "state",
    "version",
    "required_action",
    "waiting_for",
    "recovery",
    "challenge_available",
    "challenge_expires_at",
}
PROHIBITED_FIELDS = {
    "pickup_id",
    "merchant_id",
    "courier_identity_id",
    "actor_identity_id",
    "events",
    "audit",
    "outbox",
    "challenge_id",
    "code_hash",
    "verification_digest",
    "updated_at",
}


def _snapshot(
    state: CustodyState,
    *,
    challenge: PickupChallenge | None = None,
) -> CustodyStatusSnapshot:
    return CustodyStatusSnapshot(
        custody=CustodyRecord(
            custody_id=CUSTODY,
            pickup_id=PICKUP,
            order_id=ORDER,
            merchant_id=MERCHANT,
            courier_identity_id=COURIER,
            state=state,
            version=list(CustodyState).index(state) + 1,
            sealed_at=None,
            verified_at=None,
            verification_method=None,
            merchant_released_at=None,
            custody_accepted_at=None,
            updated_at=NOW,
        ),
        challenge=challenge,
    )


def _challenge(*, expires_at: datetime, used: bool = False) -> PickupChallenge:
    return PickupChallenge(
        challenge_id=uuid4(),
        custody_id=CUSTODY,
        expires_at=expires_at,
        used_at=NOW if used else None,
    )


def test_actor_status_models_are_frozen_exact_allowlists() -> None:
    assert set(MerchantCustodyStatus.model_fields) == COMMON_FIELDS
    assert set(CourierCustodyStatus.model_fields) == COMMON_FIELDS | {
        "supported_verification_methods"
    }
    for model in (MerchantCustodyStatus, CourierCustodyStatus):
        assert model.model_config["frozen"] is True
        assert model.model_config["extra"] == "forbid"
        assert not (set(model.model_fields) & PROHIBITED_FIELDS)
        with pytest.raises(ValidationError):
            model.model_validate({"internal_event_history": []})


def test_routes_bind_exact_actor_specific_response_models() -> None:
    routes = {
        route.path: route
        for route in create_custody_router(cast(CustodyApplication, object())).routes
        if isinstance(route, APIRoute)
    }
    merchant_path = "/mobile/merchants/{merchant_id}/orders/{order_id}/custody"
    courier_path = "/mobile/courier-pickups/{pickup_id}/custody"
    assert routes[merchant_path].response_model is MerchantCustodyStatus
    assert routes[courier_path].response_model is CourierCustodyStatus
    assert "courier_id" not in courier_path


@pytest.mark.parametrize(
    ("internal", "status", "public"),
    [
        ("custody_not_found", 404, "custody_unavailable"),
        ("access_denied", 403, "access_denied"),
        (
            "custody_activation_conflict",
            503,
            "custody_temporarily_unavailable",
        ),
    ],
)
def test_status_errors_are_bounded(internal, status, public) -> None:
    def fail():
        raise CustodyConflict(internal)

    with pytest.raises(HTTPException) as captured:
        _status_call(fail)
    assert captured.value.status_code == status
    assert captured.value.detail == {"code": public}


@pytest.mark.parametrize(
    (
        "state",
        "merchant_action",
        "courier_action",
        "waiting_for",
    ),
    [
        (
            CustodyState.WAITING,
            MerchantCustodyRequiredAction.SEAL_ORDER,
            CourierCustodyRequiredAction.WAIT_FOR_MERCHANT,
            CustodyWaitingFor.MERCHANT,
        ),
        (
            CustodyState.SEALED,
            MerchantCustodyRequiredAction.WAIT_FOR_COURIER,
            CourierCustodyRequiredAction.VERIFY_PICKUP,
            CustodyWaitingFor.COURIER,
        ),
        (
            CustodyState.VERIFIED,
            MerchantCustodyRequiredAction.RELEASE_ORDER,
            CourierCustodyRequiredAction.WAIT_FOR_MERCHANT,
            CustodyWaitingFor.MERCHANT,
        ),
        (
            CustodyState.RELEASED,
            MerchantCustodyRequiredAction.WAIT_FOR_COURIER,
            CourierCustodyRequiredAction.ACCEPT_CUSTODY,
            CustodyWaitingFor.COURIER,
        ),
        (
            CustodyState.ACCEPTED,
            MerchantCustodyRequiredAction.HANDOFF_COMPLETE,
            CourierCustodyRequiredAction.HANDOFF_COMPLETE,
            None,
        ),
    ],
)
def test_state_maps_to_exact_actor_actions(
    state,
    merchant_action,
    courier_action,
    waiting_for,
) -> None:
    challenge = (
        _challenge(expires_at=NOW + timedelta(minutes=5))
        if state is CustodyState.SEALED
        else None
    )
    snapshot = _snapshot(state, challenge=challenge)
    merchant = _merchant_status(snapshot, now=NOW)
    courier = _courier_status(snapshot, now=NOW)
    assert merchant.required_action is merchant_action
    assert courier.required_action is courier_action
    assert merchant.waiting_for is waiting_for
    assert courier.waiting_for is waiting_for
    assert merchant.model_dump().keys() == COMMON_FIELDS
    assert not (merchant.model_dump().keys() & PROHIBITED_FIELDS)
    assert not (courier.model_dump().keys() & PROHIBITED_FIELDS)


@pytest.mark.parametrize(
    ("challenge", "recovery"),
    [
        (
            _challenge(expires_at=NOW - timedelta(seconds=1)),
            CustodyRecoveryCategory.VERIFICATION_EXPIRED,
        ),
        (None, CustodyRecoveryCategory.TEMPORARILY_UNAVAILABLE),
        (
            _challenge(expires_at=NOW + timedelta(minutes=5), used=True),
            CustodyRecoveryCategory.TEMPORARILY_UNAVAILABLE,
        ),
    ],
)
def test_unusable_challenge_is_bounded_and_does_not_guess_next_action(
    challenge, recovery
) -> None:
    snapshot = _snapshot(CustodyState.SEALED, challenge=challenge)
    merchant = _merchant_status(snapshot, now=NOW)
    courier = _courier_status(snapshot, now=NOW)
    assert merchant.required_action is MerchantCustodyRequiredAction.NONE
    assert courier.required_action is CourierCustodyRequiredAction.NONE
    assert merchant.waiting_for is None
    assert courier.waiting_for is None
    assert merchant.recovery is recovery
    assert courier.recovery is recovery
    assert merchant.challenge_available is False
    assert courier.challenge_available is False
    assert courier.supported_verification_methods == ()


def test_verification_methods_are_disclosed_only_for_current_verify_action() -> None:
    courier = _courier_status(
        _snapshot(
            CustodyState.SEALED,
            challenge=_challenge(expires_at=NOW + timedelta(minutes=5)),
        ),
        now=NOW,
    )
    assert courier.required_action is CourierCustodyRequiredAction.VERIFY_PICKUP
    assert tuple(value.value for value in courier.supported_verification_methods) == (
        "qr_code",
        "barcode",
    )
    assert (
        _courier_status(
            _snapshot(CustodyState.WAITING), now=NOW
        ).supported_verification_methods
        == ()
    )


class _Unit:
    def __init__(self, *, assignment_valid: bool = True, custody=None) -> None:
        assignment_state = (
            CourierAssignmentState.ASSIGNED
            if assignment_valid
            else CourierAssignmentState.RELEASED
        )
        self.pickup = SimpleNamespace(
            pickup_id=PICKUP,
            order_id=ORDER,
            merchant_id=MERCHANT,
            dispatch_id=DISPATCH,
            assignment_id=ASSIGNMENT,
            assignment_version=1,
            assigned_courier_identity_id=COURIER,
        )
        self.dispatch = SimpleNamespace(
            dispatch_id=DISPATCH,
            order_id=ORDER,
            merchant_id=MERCHANT,
            state=CourierDispatchState.ASSIGNED,
            active_assignment_id=ASSIGNMENT,
            assigned_courier_identity_id=COURIER,
        )
        self.assignment = SimpleNamespace(
            assignment_id=ASSIGNMENT,
            dispatch_id=DISPATCH,
            courier_identity_id=COURIER,
            state=assignment_state,
            version=1,
        )
        self.courier_pickup = SimpleNamespace(get=lambda *args, **kwargs: self.pickup)
        self.courier_dispatch = SimpleNamespace(
            get=lambda *args, **kwargs: self.dispatch,
            get_assignment=lambda *args, **kwargs: self.assignment,
        )
        self.custody = SimpleNamespace(
            status_by_pickup=lambda pickup_id: custody,
            status_by_order=lambda order_id: custody,
        )
        self.merchants = SimpleNamespace(
            get_profile=lambda *args, **kwargs: SimpleNamespace(
                owner_identity_id=MERCHANT, state=MerchantState.APPROVED
            )
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Composition:
    def __init__(self, unit: _Unit) -> None:
        self.unit = unit

    def unit_of_work(self):
        return self.unit


def _subject(identity_id: UUID, identity_type: IdentityType) -> AuthorizationSubject:
    actor = (
        ActorType.DRIVER if identity_type is IdentityType.DRIVER else ActorType.SERVICE
    )
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=identity_type,
        actor_type=actor,
    )


def test_assigned_courier_discovers_exact_custody_by_pickup() -> None:
    snapshot = _snapshot(CustodyState.WAITING)
    application = CustodyApplication(
        _Composition(_Unit(custody=snapshot)),
        verification_pepper=b"status-contract-pepper" * 2,
    )
    assert (
        application.courier_detail(
            _subject(COURIER, IdentityType.DRIVER), pickup_id=PICKUP
        )
        == snapshot
    )


@pytest.mark.parametrize(
    "unit,identity",
    [
        (_Unit(custody=_snapshot(CustodyState.WAITING)), uuid4()),
        (
            _Unit(assignment_valid=False, custody=_snapshot(CustodyState.WAITING)),
            COURIER,
        ),
        (_Unit(custody=None), COURIER),
    ],
)
def test_wrong_stale_or_missing_courier_custody_fails_closed(unit, identity) -> None:
    application = CustodyApplication(
        _Composition(unit), verification_pepper=b"status-contract-pepper" * 2
    )
    with pytest.raises(CustodyConflict, match="custody_not_found"):
        application.courier_detail(
            _subject(identity, IdentityType.DRIVER), pickup_id=PICKUP
        )


def test_merchant_read_preserves_owner_boundary() -> None:
    snapshot = _snapshot(CustodyState.WAITING)
    application = CustodyApplication(
        _Composition(_Unit(custody=snapshot)),
        verification_pepper=b"status-contract-pepper" * 2,
    )
    assert (
        application.merchant_detail(
            _subject(MERCHANT, IdentityType.MERCHANT),
            merchant_id=MERCHANT,
            order_id=ORDER,
        )
        == snapshot
    )
    with pytest.raises(CustodyConflict, match="access_denied"):
        application.merchant_detail(
            _subject(uuid4(), IdentityType.MERCHANT),
            merchant_id=MERCHANT,
            order_id=ORDER,
        )
