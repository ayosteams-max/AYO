from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupExceptionReason,
    CourierPickupView,
)
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import MerchantState
from BACKEND.routes.courier_pickup import create_courier_pickup_router
from tests.test_courier_pickup_increment1 import application, subject

NOW = datetime(2026, 8, 5, tzinfo=UTC)


def _routes(application_value: CourierPickupApplication) -> list[APIRoute]:
    return [
        route
        for route in create_courier_pickup_router(application_value).routes
        if isinstance(route, APIRoute)
    ]


def test_all_four_routes_are_authenticated_without_eager_permission_metadata() -> None:
    app_value, value, courier_id, _ = application(permissions=set())
    routes = _routes(app_value)
    assert len(routes) == 4
    assert all(
        not hasattr(route.endpoint, "__ayo_permission_requirement__")
        for route in routes
    )

    api = FastAPI()
    api.include_router(create_courier_pickup_router(app_value))
    response = TestClient(api).get(f"/mobile/courier-pickups/{value.pickup_id}")
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "authentication_required"}}
    assert courier_id == value.assigned_courier_identity_id


class _NeverRouteEnforcer:
    def enforce(self, request: Request, requirement: object) -> None:
        del request, requirement
        raise AssertionError("Courier Pickup route performed eager authorization")


class _RouteApplication:
    def __init__(self, view: CourierPickupView) -> None:
        self.view = view

    def merchant_detail(self, *args: object, **kwargs: object) -> CourierPickupView:
        return self.view

    def merchant_acknowledge(
        self, *args: object, **kwargs: object
    ) -> CourierPickupView:
        return self.view

    def courier_detail(self, *args: object, **kwargs: object) -> CourierPickupView:
        return self.view

    def courier_command(self, *args: object, **kwargs: object) -> CourierPickupView:
        return self.view


def test_routes_delegate_without_lookup_or_authorization_transaction() -> None:
    app_value, value, courier_id, merchant_owner = application(
        permissions={"courier_pickup.manage_assigned"}
    )
    unit = app_value._composition.unit
    view = unit.courier_pickup._view()
    route_application = cast(CourierPickupApplication, _RouteApplication(view))
    api = FastAPI()
    api.state.authorization_enforcer = _NeverRouteEnforcer()

    @api.middleware("http")
    async def authenticated_subject(request: Request, call_next):
        request.state.authorization_subject = subject(courier_id, IdentityType.DRIVER)
        return await call_next(request)

    api.include_router(create_courier_pickup_router(route_application))
    client = TestClient(api)
    responses = (
        client.get(
            f"/mobile/merchants/{value.merchant_id}/orders/{value.order_id}/courier-pickup"
        ),
        client.post(
            f"/mobile/merchants/{value.merchant_id}/courier-pickups/{value.pickup_id}/acknowledge",
            headers={"Idempotency-Key": "merchant-command-0001"},
            json={"expected_version": 1, "action": "acknowledge_arrival"},
        ),
        client.get(f"/mobile/courier-pickups/{value.pickup_id}"),
        client.post(
            f"/mobile/courier-pickups/{value.pickup_id}/actions",
            headers={"Idempotency-Key": "courier-command-0001"},
            json={"expected_version": 1, "action": "start_travel"},
        ),
    )
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert merchant_owner != courier_id


def _record_permissions(app_value: CourierPickupApplication) -> list[str]:
    unit = app_value._composition.unit
    permissions: list[str] = []

    def deny(identity_id: UUID, permission: str, *, at: datetime) -> bool:
        del identity_id, at
        permissions.append(permission)
        return False

    unit.authorization = SimpleNamespace(has_permission=deny)
    return permissions


def test_status_reads_check_ownership_before_exact_permission() -> None:
    app_value, value, courier_id, merchant_owner = application(permissions=set())
    unit = app_value._composition.unit
    unit.courier_pickup.get_by_order = lambda order_id: (
        unit.courier_pickup._view() if order_id == value.order_id else None
    )
    permissions = _record_permissions(app_value)

    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.courier_detail(
            subject(uuid4(), IdentityType.DRIVER), pickup_id=value.pickup_id
        )
    assert permissions == []
    with pytest.raises(CourierPickupConflict, match="^access_denied$"):
        app_value.courier_detail(
            subject(courier_id, IdentityType.DRIVER), pickup_id=value.pickup_id
        )
    assert permissions == ["courier_pickup.manage_assigned"]

    permissions.clear()
    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.merchant_detail(
            subject(uuid4(), IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=value.order_id,
        )
    assert permissions == []
    with pytest.raises(CourierPickupConflict, match="^access_denied$"):
        app_value.merchant_detail(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=value.order_id,
        )
    assert permissions == ["courier_pickup.read_own_merchant"]


def test_missing_merchant_pickup_is_unavailable_before_permission_lookup() -> None:
    app_value, value, _, merchant_owner = application(permissions=set())
    unit = app_value._composition.unit
    unit.courier_pickup.get_by_order = lambda order_id: None
    permissions = _record_permissions(app_value)
    original_pickup = unit.courier_pickup.value

    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.merchant_detail(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=uuid4(),
        )

    assert permissions == []
    assert unit.courier_pickup.value == original_pickup
    assert unit.courier_pickup.replays == {}
    assert unit.audit_events == []


def test_merchant_status_evidence_remains_owner_approved_and_pickup_bound() -> None:
    app_value, value, _, merchant_owner = application(
        permissions={"courier_pickup.read_own_merchant"}
    )
    unit = app_value._composition.unit
    unit.courier_pickup.get_by_order = lambda order_id: (
        unit.courier_pickup._view() if order_id == value.order_id else None
    )
    original_pickup = unit.courier_pickup.value

    assert (
        app_value.merchant_detail(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=value.order_id,
        ).pickup
        == original_pickup
    )

    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.merchant_detail(
            subject(uuid4(), IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=value.order_id,
        )

    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.merchant_detail(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=uuid4(),
            order_id=value.order_id,
        )

    unit.merchants.get_profile = lambda merchant_id, lock=False: SimpleNamespace(
        merchant_id=merchant_id,
        owner_identity_id=merchant_owner,
        state=MerchantState.SUSPENDED,
    )
    with pytest.raises(CourierPickupConflict, match="^merchant_unavailable$"):
        app_value.merchant_detail(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=value.order_id,
        )

    unit.merchants.get_profile = lambda merchant_id, lock=False: SimpleNamespace(
        merchant_id=merchant_id,
        owner_identity_id=merchant_owner,
        state=MerchantState.APPROVED,
    )
    unit.courier_pickup.value = original_pickup.model_copy(
        update={"merchant_id": uuid4()}
    )
    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.merchant_detail(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            order_id=value.order_id,
        )

    assert unit.courier_pickup.replays == {}
    assert unit.audit_events == []
    assert unit.custody.value is None


def test_missing_courier_pickup_is_unavailable_before_permission_lookup() -> None:
    app_value, _, courier_id, _ = application(
        permissions={"courier_pickup.manage_assigned"}
    )
    unit = app_value._composition.unit
    permissions = _record_permissions(app_value)
    original_pickup = unit.courier_pickup.value

    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.courier_detail(
            subject(courier_id, IdentityType.DRIVER), pickup_id=uuid4()
        )

    assert permissions == []
    assert unit.courier_pickup.value == original_pickup
    assert unit.courier_pickup.replays == {}
    assert unit.audit_events == []


@pytest.mark.parametrize(
    ("actor", "expected_permission"),
    [
        (CourierPickupAction.START_TRAVEL, "courier_pickup.manage_assigned"),
        (CourierPickupAction.MARK_ARRIVED, "courier_pickup.manage_assigned"),
        (CourierPickupAction.CORRECT_ARRIVAL, "courier_pickup.correct_assigned"),
        (CourierPickupAction.END_ATTEMPT, "courier_pickup.close_assigned"),
    ],
)
def test_courier_commands_select_permission_after_locked_assignment(
    actor: CourierPickupAction, expected_permission: str
) -> None:
    app_value, value, courier_id, _ = application(permissions=set())
    unit = app_value._composition.unit
    permissions = _record_permissions(app_value)
    locks: list[bool] = []
    original_get = unit.courier_pickup.get

    def get(pickup_id: UUID, *, lock: bool = False):
        locks.append(lock)
        return original_get(pickup_id, lock=lock)

    unit.courier_pickup.get = get
    kwargs: dict[str, Any] = {}
    if actor is CourierPickupAction.END_ATTEMPT:
        kwargs["reason"] = CourierPickupExceptionReason.COURIER_UNABLE
    with pytest.raises(CourierPickupConflict, match="^access_denied$"):
        app_value.courier_command(
            subject(courier_id, IdentityType.DRIVER),
            pickup_id=value.pickup_id,
            expected_version=1,
            action=actor,
            idempotency_key=f"courier-{actor.value}-0001",
            at=NOW,
            **kwargs,
        )
    assert locks == [True]
    assert permissions == [expected_permission]


@pytest.mark.parametrize(
    ("action", "expected_permission"),
    [
        (
            CourierPickupAction.ACKNOWLEDGE_ARRIVAL,
            "courier_pickup.acknowledge_own_merchant",
        ),
        (CourierPickupAction.CORRECT_WAITING, "courier_pickup.correct_own_merchant"),
        (CourierPickupAction.END_ATTEMPT, "courier_pickup.close_own_merchant"),
    ],
)
def test_merchant_commands_select_permission_after_locked_ownership(
    action: CourierPickupAction, expected_permission: str
) -> None:
    app_value, value, _, merchant_owner = application(permissions=set())
    permissions = _record_permissions(app_value)
    kwargs: dict[str, Any] = {}
    if action is CourierPickupAction.END_ATTEMPT:
        kwargs["reason"] = CourierPickupExceptionReason.ORDER_NOT_READY
    with pytest.raises(CourierPickupConflict, match="^access_denied$"):
        app_value.merchant_acknowledge(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=value.merchant_id,
            pickup_id=value.pickup_id,
            expected_version=1,
            action=action,
            idempotency_key=f"merchant-{action.value}-0001",
            at=NOW,
            **kwargs,
        )
    assert permissions == [expected_permission]


def test_wrong_owner_is_unavailable_even_when_baseline_permission_is_held() -> None:
    app_value, value, _, _ = application(
        permissions={
            "courier_pickup.manage_assigned",
            "courier_pickup.acknowledge_own_merchant",
        }
    )
    permissions = _record_permissions(app_value)
    wrong = subject(uuid4(), IdentityType.DRIVER)
    with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
        app_value.courier_command(
            wrong,
            pickup_id=value.pickup_id,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key="wrong-owner-command-0001",
            at=NOW,
        )
    assert permissions == []
