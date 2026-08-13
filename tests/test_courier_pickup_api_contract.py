from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationEnforcer
from BACKEND.config.settings import Settings
from BACKEND.courier_pickup.application import (
    CourierPickupApplication,
    CourierPickupMerchantRead,
)
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import CourierPickupState, CourierPickupView
from BACKEND.custody.application import CustodyApplication
from BACKEND.identity.models import IdentityType
from BACKEND.main import (
    CourierPickupPlatformActivation,
    CustodyPlatformActivation,
    create_app,
)
from BACKEND.routes import courier_pickup as courier_pickup_routes
from BACKEND.routes.courier_pickup import (
    MERCHANT_PRESENTATION_ACTION_BY_STATE,
    CourierPickupCourierCommandResult,
    CourierPickupCourierStatus,
    CourierPickupMerchantCommandResult,
    CourierPickupMerchantPresentationAction,
    CourierPickupMerchantStatus,
    _call,
    _courier_command_result,
    _courier_status,
    _merchant_command_result,
    _merchant_status,
    create_courier_pickup_router,
)
from tests.test_courier_pickup_increment1 import application, subject

COURIER_FIELDS = {
    "pickup_id",
    "state",
    "version",
    "assigned_at",
    "travelling_at",
    "arrived_at",
    "merchant_acknowledged_at",
    "waiting_duration_seconds",
    "terminal_reason",
    "updated_at",
}
COURIER_STATUS_FIELDS = COURIER_FIELDS | {"presentation_action"}
MERCHANT_FIELDS = COURIER_FIELDS - {"assigned_at", "travelling_at"}
MERCHANT_STATUS_FIELDS = MERCHANT_FIELDS | {"presentation_action"}
PROHIBITED_FIELDS = {
    "merchant_id",
    "assigned_courier_identity_id",
    "order_id",
    "dispatch_id",
    "assignment_id",
    "assignment_message_id",
    "assignment_version",
    "actor_identity_id",
    "acting_for_identity_id",
    "authority_basis",
    "permission",
    "policy_code",
    "policy_version",
    "source_reference",
    "source_version",
    "events",
    "evidence",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "request_hash",
    "replay_snapshot",
    "location_evidence_reference",
    "latitude",
    "longitude",
}


class _Resolver:
    def __init__(self, value: AuthorizationSubject | None) -> None:
        self.value = value

    async def resolve(self, request) -> AuthorizationSubject | None:
        del request
        return self.value


class _NeverEnforcer:
    def enforce(self, request, requirement) -> None:
        del request, requirement
        raise AssertionError("Courier Pickup route performed eager authorization")


class _RouteApplication:
    def __init__(
        self, view: CourierPickupView | None = None, conflict: str | None = None
    ) -> None:
        self.view = view
        self.conflict = conflict

    def _result(self) -> CourierPickupView:
        if self.conflict is not None:
            raise CourierPickupConflict(self.conflict)
        assert self.view is not None
        return self.view

    def merchant_detail(self, *args, **kwargs) -> CourierPickupMerchantRead:
        return CourierPickupMerchantRead(view=self._result(), current_assignment=True)

    def merchant_acknowledge(self, *args, **kwargs) -> CourierPickupView:
        return self._result()

    def courier_detail(self, *args, **kwargs) -> CourierPickupView:
        return self._result()

    def courier_command(self, *args, **kwargs) -> CourierPickupView:
        return self._result()


def _view() -> tuple[CourierPickupView, UUID, UUID]:
    app, pickup, courier_id, merchant_owner = application(
        permissions={
            "courier_pickup.manage_assigned",
            "courier_pickup.read_own_merchant",
            "courier_pickup.acknowledge_own_merchant",
        }
    )
    del pickup
    return app._composition.unit.courier_pickup._view(), courier_id, merchant_owner


def _client(
    route_application: _RouteApplication,
    actor: AuthorizationSubject | None,
) -> TestClient:
    activation = CourierPickupPlatformActivation(
        application=cast(CourierPickupApplication, route_application),
        subject_resolver=_Resolver(actor),
        authorization_enforcer=cast(AuthorizationEnforcer, _NeverEnforcer()),
    )
    app = create_app(
        Settings(
            COURIER_PICKUP_PLATFORM_ENABLED=True,
            CUSTODY_PLATFORM_ENABLED=True,
        ),
        courier_pickup_platform=activation,
        custody_platform=CustodyPlatformActivation(
            application=cast(CustodyApplication, route_application),
            subject_resolver=_Resolver(actor),
            authorization_enforcer=cast(AuthorizationEnforcer, _NeverEnforcer()),
        ),
    )
    return TestClient(app)


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        (CourierPickupCourierCommandResult, COURIER_FIELDS),
        (CourierPickupCourierStatus, COURIER_STATUS_FIELDS),
        (CourierPickupMerchantCommandResult, MERCHANT_FIELDS),
        (CourierPickupMerchantStatus, MERCHANT_STATUS_FIELDS),
    ],
)
def test_public_models_are_frozen_closed_exact_allowlists(model, fields) -> None:
    assert set(model.model_fields) == fields
    assert model.model_config["frozen"] is True
    assert model.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        model.model_validate({"unexpected_internal_field": "private"})


def test_pickup_activation_fails_closed_without_custody_feature_gate() -> None:
    with pytest.raises(RuntimeError, match="requires Custody Platform"):
        create_app(Settings(COURIER_PICKUP_PLATFORM_ENABLED=True))


def test_distinct_pure_mappers_emit_only_exact_caller_fields() -> None:
    view, _, _ = _view()
    before = view.model_dump_json()
    results = (
        _courier_command_result(view),
        _courier_status(view),
        _merchant_command_result(view),
        _merchant_status(CourierPickupMerchantRead(view, current_assignment=True)),
    )
    assert [set(result.model_dump()) for result in results] == [
        COURIER_FIELDS,
        COURIER_STATUS_FIELDS,
        MERCHANT_FIELDS,
        MERCHANT_STATUS_FIELDS,
    ]
    assert len({type(result) for result in results}) == 4
    assert view.model_dump_json() == before
    serialized = " ".join(result.model_dump_json() for result in results)
    assert all(field not in serialized for field in PROHIBITED_FIELDS)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("courier_assigned", "start_travel"),
        ("travelling_to_merchant", "mark_arrived"),
        ("arrived_at_merchant", "none"),
        ("waiting_for_pickup", "none"),
        ("pickup_attempt_ended_before_custody", "none"),
    ],
)
def test_courier_status_derives_only_bounded_presentation_action(
    state, expected
) -> None:
    view, _, _ = _view()
    pickup = view.pickup.model_copy(update={"state": CourierPickupState(state)})
    assert (
        _courier_status(view.model_copy(update={"pickup": pickup})).presentation_action
        == expected
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (CourierPickupState.ASSIGNED, "none"),
        (CourierPickupState.TRAVELLING, "none"),
        (CourierPickupState.ARRIVED, "acknowledge_arrival"),
        (CourierPickupState.WAITING, "none"),
        (CourierPickupState.ENDED_BEFORE_CUSTODY, "none"),
    ],
)
def test_merchant_status_derives_only_bounded_presentation_action(
    state: CourierPickupState, expected: str
) -> None:
    view, _, _ = _view()
    pickup = view.pickup.model_copy(update={"state": state})
    assert (
        _merchant_status(
            CourierPickupMerchantRead(
                view.model_copy(update={"pickup": pickup}), current_assignment=True
            )
        ).presentation_action
        == expected
    )


def test_arrived_merchant_status_suppresses_action_for_stale_assignment() -> None:
    view, _, _ = _view()
    pickup = view.pickup.model_copy(update={"state": CourierPickupState.ARRIVED})
    arrived = view.model_copy(update={"pickup": pickup})

    assert (
        _merchant_status(
            CourierPickupMerchantRead(arrived, current_assignment=True)
        ).presentation_action
        == "acknowledge_arrival"
    )
    assert (
        _merchant_status(
            CourierPickupMerchantRead(arrived, current_assignment=False)
        ).presentation_action
        == "none"
    )


def test_merchant_presentation_matrix_is_exact_and_exhaustive() -> None:
    assert set(MERCHANT_PRESENTATION_ACTION_BY_STATE) == set(CourierPickupState)
    assert set(CourierPickupMerchantPresentationAction) == {
        CourierPickupMerchantPresentationAction.ACKNOWLEDGE_ARRIVAL,
        CourierPickupMerchantPresentationAction.NONE,
    }


def test_first_and_replayed_internal_views_map_to_identical_public_json() -> None:
    first, _, _ = _view()
    replay = CourierPickupView.model_validate_json(first.model_dump_json())
    assert _courier_command_result(first).model_dump_json() == (
        _courier_command_result(replay).model_dump_json()
    )
    assert _merchant_command_result(first).model_dump_json() == (
        _merchant_command_result(replay).model_dump_json()
    )


def test_routes_and_openapi_bind_only_the_four_closed_response_models() -> None:
    router = create_courier_pickup_router(
        cast(CourierPickupApplication, SimpleNamespace())
    )
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert [route.response_model for route in routes] == [
        CourierPickupMerchantStatus,
        CourierPickupMerchantCommandResult,
        CourierPickupCourierStatus,
        CourierPickupCourierCommandResult,
    ]
    assert all(
        not hasattr(route.endpoint, "__ayo_permission_requirement__")
        for route in routes
    )
    view, courier_id, _ = _view()
    client = _client(_RouteApplication(view), subject(courier_id, IdentityType.DRIVER))
    schemas = cast(FastAPI, client.app).openapi()["components"]["schemas"]
    expected = {
        "CourierPickupCourierCommandResult": COURIER_FIELDS,
        "CourierPickupCourierStatus": COURIER_STATUS_FIELDS,
        "CourierPickupMerchantCommandResult": MERCHANT_FIELDS,
        "CourierPickupMerchantStatus": MERCHANT_STATUS_FIELDS,
    }
    for name, fields in expected.items():
        assert set(schemas[name]["properties"]) == fields
        assert schemas[name]["additionalProperties"] is False
    assert not {
        "CourierPickupView",
        "CourierPickupRecord",
        "CourierPickupEvent",
        "CourierPickupEvidence",
    }.intersection(schemas)


def test_composed_http_returns_exact_public_models_and_error_envelopes() -> None:
    view, courier_id, _ = _view()
    client = _client(_RouteApplication(view), subject(courier_id, IdentityType.DRIVER))
    base = "/api"
    responses = (
        client.get(
            f"{base}/mobile/merchants/{view.pickup.merchant_id}/orders/"
            f"{view.pickup.order_id}/courier-pickup"
        ),
        client.post(
            f"{base}/mobile/merchants/{view.pickup.merchant_id}/courier-pickups/"
            f"{view.pickup.pickup_id}/acknowledge",
            headers={"Idempotency-Key": "merchant-command-0001"},
            json={"expected_version": 3, "action": "acknowledge_arrival"},
        ),
        client.get(f"{base}/mobile/courier-pickups/{view.pickup.pickup_id}"),
        client.post(
            f"{base}/mobile/courier-pickups/{view.pickup.pickup_id}/actions",
            headers={"Idempotency-Key": "courier-command-0001"},
            json={"expected_version": 3, "action": "start_travel"},
        ),
    )
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert [set(response.json()) for response in responses] == [
        MERCHANT_STATUS_FIELDS,
        MERCHANT_FIELDS,
        COURIER_STATUS_FIELDS,
        COURIER_FIELDS,
    ]
    unauthenticated = _client(_RouteApplication(view), None).get(
        f"{base}/mobile/courier-pickups/{view.pickup.pickup_id}"
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {"error": {"code": "authentication_required"}}

    invalid_action = client.post(
        f"{base}/mobile/merchants/{view.pickup.merchant_id}/courier-pickups/"
        f"{view.pickup.pickup_id}/acknowledge",
        headers={"Idempotency-Key": "merchant-invalid-action-0001"},
        json={"expected_version": 3, "action": "start_travel"},
    )
    assert invalid_action.status_code == 409
    assert invalid_action.json() == {
        "error": {"code": "courier_pickup_transition_not_allowed"}
    }


@pytest.mark.parametrize(
    ("internal", "status", "public"),
    [
        ("courier_pickup_unavailable", 404, "courier_pickup_unavailable"),
        ("access_denied", 403, "access_denied"),
        ("unreviewed_database_identity_trace", 500, "request_rejected"),
    ],
)
def test_composed_http_never_exposes_internal_conflict_text(
    internal, status, public, caplog
) -> None:
    _, courier_id, _ = _view()
    with caplog.at_level("ERROR"):
        response = _client(
            _RouteApplication(conflict=internal),
            subject(courier_id, IdentityType.DRIVER),
        ).get(f"/api/mobile/courier-pickups/{uuid4()}")
    assert response.status_code == status
    assert response.json() == {"error": {"code": public}}
    if internal != public:
        assert internal not in response.text
        assert internal not in caplog.text


@pytest.mark.parametrize(
    ("internal", "status", "public"),
    [
        ("courier_pickup_unavailable", 404, "courier_pickup_unavailable"),
        ("courier_pickup_not_found", 404, "courier_pickup_unavailable"),
        ("access_denied", 403, "access_denied"),
        ("idempotency_conflict", 409, "idempotency_conflict"),
        (
            "courier_pickup_version_conflict",
            409,
            "courier_pickup_version_conflict",
        ),
        (
            "invalid_courier_pickup_transition",
            409,
            "courier_pickup_transition_not_allowed",
        ),
        (
            "location_evidence_stale_or_invalid",
            409,
            "location_evidence_stale_or_invalid",
        ),
        (
            "idempotency_record_incompatible",
            409,
            "idempotency_replay_unavailable",
        ),
        (
            "courier_pickup_assignment_invalid",
            409,
            "courier_pickup_temporarily_unavailable",
        ),
    ],
)
def test_reviewed_conflicts_have_explicit_minimal_public_mappings(
    internal, status, public
) -> None:
    def fail() -> None:
        raise CourierPickupConflict(internal)

    with pytest.raises(HTTPException) as captured:
        _call(fail)
    assert captured.value.status_code == status
    assert captured.value.detail == {"code": public}


def test_unknown_conflict_is_sanitized_and_safely_logged(monkeypatch) -> None:
    sensitive = "unknown_actor_merchant_hash_table_trace"
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def capture_error(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    def fail() -> None:
        raise CourierPickupConflict(sensitive)

    monkeypatch.setattr(courier_pickup_routes.logger, "error", capture_error)
    with pytest.raises(HTTPException) as captured:
        _call(fail)

    assert captured.value.status_code == 500
    assert captured.value.detail == {"code": "request_rejected"}
    assert calls == [(("unclassified courier pickup conflict",), {})]
    assert all(sensitive not in repr(args) for args, _ in calls)
    assert all(sensitive not in repr(kwargs) for _, kwargs in calls)
    assert sensitive not in str(captured.value.detail)
