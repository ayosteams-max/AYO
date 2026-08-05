from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupEvent,
    CourierPickupEvidence,
    CourierPickupEvidenceKind,
    CourierPickupRecord,
    CourierPickupState,
    CourierPickupView,
)
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import MerchantState
from BACKEND.routes.courier_pickup import (
    CourierPickupCourierCommandResult,
    CourierPickupCourierStatus,
    CourierPickupMerchantCommandResult,
    CourierPickupMerchantStatus,
    _call,
    _courier_command_result,
    _courier_status,
    _merchant_command_result,
    _merchant_status,
    create_courier_pickup_router,
)
from BACKEND.routes.courier_pickup import (
    _subject as route_subject,
)

NOW = datetime(2026, 8, 5, 8, tzinfo=UTC)
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
MERCHANT_FIELDS = COURIER_FIELDS - {"assigned_at", "travelling_at"}


def _subject(identity_id: UUID, identity_type: IdentityType) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=identity_type,
        actor_type=(
            ActorType.DRIVER
            if identity_type is IdentityType.DRIVER
            else ActorType.SERVICE
        ),
    )


def _view() -> CourierPickupView:
    pickup_id = uuid4()
    actor_id = uuid4()
    record = CourierPickupRecord(
        pickup_id=pickup_id,
        dispatch_id=uuid4(),
        assignment_id=uuid4(),
        assignment_version=2,
        attempt_number=1,
        order_id=uuid4(),
        merchant_id=uuid4(),
        assigned_courier_identity_id=actor_id,
        assignment_message_id=uuid4(),
        state=CourierPickupState.ARRIVED,
        version=3,
        assigned_at=NOW,
        travelling_at=NOW,
        arrived_at=NOW,
        merchant_acknowledged_at=None,
        waiting_duration_seconds=None,
        terminal_reason=None,
        updated_at=NOW,
    )
    event = CourierPickupEvent(
        event_id=uuid4(),
        pickup_id=pickup_id,
        order_id=record.order_id,
        event_type="courier_arrived_at_merchant.v1",
        from_state=CourierPickupState.TRAVELLING,
        to_state=CourierPickupState.ARRIVED,
        actor_identity_id=actor_id,
        version=3,
        occurred_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )
    evidence = CourierPickupEvidence(
        evidence_id=uuid4(),
        pickup_id=pickup_id,
        pickup_version=3,
        kind=CourierPickupEvidenceKind.ARRIVAL_DECLARED,
        actor_identity_id=actor_id,
        merchant_id=record.merchant_id,
        authority_basis="assigned_courier",
        source_reference=uuid4(),
        source_version=1,
        occurred_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )
    return CourierPickupView(pickup=record, events=(event,), evidence=(evidence,))


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        (CourierPickupCourierCommandResult, COURIER_FIELDS),
        (CourierPickupCourierStatus, COURIER_FIELDS),
        (CourierPickupMerchantCommandResult, MERCHANT_FIELDS),
        (CourierPickupMerchantStatus, MERCHANT_FIELDS),
    ],
)
def test_public_models_are_closed_explicit_allowlists(model, fields) -> None:
    assert set(model.model_fields) == fields
    assert model.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        model.model_validate({"unexpected_internal_field": "private"})


def test_caller_specific_mappers_do_not_leak_internal_fields() -> None:
    view = _view()
    results = (
        _courier_command_result(view),
        _courier_status(view),
        _merchant_command_result(view),
        _merchant_status(view),
    )
    assert set(results[0].model_dump()) == COURIER_FIELDS
    assert set(results[1].model_dump()) == COURIER_FIELDS
    assert set(results[2].model_dump()) == MERCHANT_FIELDS
    assert set(results[3].model_dump()) == MERCHANT_FIELDS
    serialized = " ".join(result.model_dump_json() for result in results)
    for prohibited in (
        "dispatch_id",
        "assignment_id",
        "merchant_id",
        "assigned_courier_identity_id",
        "actor_identity_id",
        "authority_basis",
        "source_reference",
        "correlation_id",
        "causation_id",
        "events",
        "evidence",
    ):
        assert prohibited not in serialized


def test_first_and_replayed_views_map_to_byte_equivalent_public_json() -> None:
    first = _view()
    replay = CourierPickupView.model_validate_json(first.model_dump_json())
    assert _courier_command_result(first).model_dump_json() == (
        _courier_command_result(replay).model_dump_json()
    )
    assert _merchant_command_result(first).model_dump_json() == (
        _merchant_command_result(replay).model_dump_json()
    )


def test_router_binds_each_operation_to_its_exact_public_model() -> None:
    application = cast(CourierPickupApplication, SimpleNamespace())
    router = create_courier_pickup_router(application)
    bindings = {
        (route.path, tuple(route.methods or ())): route.response_model
        for route in router.routes
        if isinstance(route, APIRoute)
    }
    assert (
        bindings[
            (
                "/mobile/merchants/{merchant_id}/orders/{order_id}/courier-pickup",
                ("GET",),
            )
        ]
        is CourierPickupMerchantStatus
    )
    assert (
        bindings[
            (
                "/mobile/merchants/{merchant_id}/courier-pickups/{pickup_id}/acknowledge",
                ("POST",),
            )
        ]
        is CourierPickupMerchantCommandResult
    )
    assert bindings[("/mobile/courier-pickups/{pickup_id}", ("GET",))] is (
        CourierPickupCourierStatus
    )
    assert bindings[("/mobile/courier-pickups/{pickup_id}/actions", ("POST",))] is (
        CourierPickupCourierCommandResult
    )


def test_openapi_exposes_only_closed_public_pickup_response_schemas() -> None:
    application = cast(CourierPickupApplication, SimpleNamespace())
    app = FastAPI()
    app.include_router(create_courier_pickup_router(application))
    schemas = app.openapi()["components"]["schemas"]
    approved = {
        "CourierPickupCourierCommandResult": COURIER_FIELDS,
        "CourierPickupCourierStatus": COURIER_FIELDS,
        "CourierPickupMerchantCommandResult": MERCHANT_FIELDS,
        "CourierPickupMerchantStatus": MERCHANT_FIELDS,
    }
    for name, fields in approved.items():
        schema = schemas[name]
        assert set(schema["properties"]) == fields
        assert schema["additionalProperties"] is False
    for prohibited_schema in (
        "CourierPickupView",
        "CourierPickupRecord",
        "CourierPickupEvent",
        "CourierPickupEvidence",
    ):
        assert prohibited_schema not in schemas


class _RouteApplication:
    def __init__(self, view: CourierPickupView) -> None:
        self.view = view

    def merchant_detail(self, *args, **kwargs) -> CourierPickupView:
        return self.view

    def merchant_acknowledge(self, *args, **kwargs) -> CourierPickupView:
        return self.view

    def courier_detail(self, *args, **kwargs) -> CourierPickupView:
        return self.view

    def courier_command(self, *args, **kwargs) -> CourierPickupView:
        return self.view


class _RouteEnforcer:
    def __init__(self, subject: AuthorizationSubject) -> None:
        self.subject = subject

    def enforce(self, request: Request, requirement) -> None:
        request.state.authorization_subject = self.subject


def test_all_four_http_adapters_execute_the_explicit_public_mappers() -> None:
    view = _view()
    subject = _subject(view.pickup.assigned_courier_identity_id, IdentityType.DRIVER)
    application = cast(CourierPickupApplication, _RouteApplication(view))
    app = FastAPI()
    app.state.authorization_enforcer = _RouteEnforcer(subject)
    app.include_router(create_courier_pickup_router(application))
    client = TestClient(app)

    merchant_status = client.get(
        f"/mobile/merchants/{view.pickup.merchant_id}/orders/{view.pickup.order_id}/courier-pickup"
    )
    merchant_command = client.post(
        f"/mobile/merchants/{view.pickup.merchant_id}/courier-pickups/{view.pickup.pickup_id}/acknowledge",
        headers={"Idempotency-Key": "merchant-command-0001"},
        json={"expected_version": 3, "action": "acknowledge_arrival"},
    )
    courier_status = client.get(f"/mobile/courier-pickups/{view.pickup.pickup_id}")
    courier_command = client.post(
        f"/mobile/courier-pickups/{view.pickup.pickup_id}/actions",
        headers={"Idempotency-Key": "courier-command-0001"},
        json={"expected_version": 3, "action": "start_travel"},
    )

    assert merchant_status.status_code == merchant_command.status_code == 200
    assert courier_status.status_code == courier_command.status_code == 200
    assert (
        set(merchant_status.json()) == set(merchant_command.json()) == MERCHANT_FIELDS
    )
    assert set(courier_status.json()) == set(courier_command.json()) == COURIER_FIELDS


def test_adapter_authentication_and_invalid_merchant_action_fail_closed() -> None:
    request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as missing_subject:
        route_subject(request)
    assert missing_subject.value.status_code == 401
    assert missing_subject.value.detail == {"code": "authentication_required"}

    view = _view()
    subject = _subject(view.pickup.assigned_courier_identity_id, IdentityType.DRIVER)
    application = cast(CourierPickupApplication, _RouteApplication(view))
    app = FastAPI()
    app.state.authorization_enforcer = _RouteEnforcer(subject)
    app.include_router(create_courier_pickup_router(application))
    response = TestClient(app).post(
        f"/mobile/merchants/{view.pickup.merchant_id}/courier-pickups/{view.pickup.pickup_id}/acknowledge",
        headers={"Idempotency-Key": "merchant-command-0002"},
        json={"expected_version": 3, "action": "start_travel"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "courier_pickup_transition_not_allowed"}
    }


@pytest.mark.parametrize(
    ("internal", "status", "public"),
    [
        ("courier_pickup_unavailable", 404, "courier_pickup_unavailable"),
        ("courier_pickup_not_found", 404, "courier_pickup_unavailable"),
        ("access_denied", 403, "access_denied"),
        ("idempotency_conflict", 409, "idempotency_conflict"),
        ("idempotency_record_incompatible", 409, "idempotency_replay_unavailable"),
        ("internal_database_detail", 409, "courier_pickup_temporarily_unavailable"),
    ],
)
def test_conflicts_map_to_minimal_safe_public_codes(internal, status, public) -> None:
    def fail() -> None:
        raise CourierPickupConflict(internal)

    with pytest.raises(HTTPException) as captured:
        _call(fail)
    assert captured.value.status_code == status
    assert captured.value.detail == {"code": public}
    assert internal not in str(captured.value.detail) or internal == public


class _ReadUnit:
    def __init__(self, view: CourierPickupView, owner: UUID) -> None:
        self.courier_pickup = SimpleNamespace(
            get=lambda pickup_id, lock=False: (
                view.pickup if pickup_id == view.pickup.pickup_id else None
            ),
            view=lambda pickup_id: view if pickup_id == view.pickup.pickup_id else None,
            get_by_order=lambda order_id: (
                view if order_id == view.pickup.order_id else None
            ),
        )
        self.merchants = SimpleNamespace(
            get_profile=lambda merchant_id, lock=False: SimpleNamespace(
                merchant_id=merchant_id,
                owner_identity_id=owner,
                state=MerchantState.APPROVED,
            )
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_missing_and_cross_owner_reads_share_the_same_internal_classification() -> None:
    view = _view()
    owner = uuid4()
    app = CourierPickupApplication(
        SimpleNamespace(unit_of_work=lambda: _ReadUnit(view, owner))
    )
    wrong_courier = _subject(uuid4(), IdentityType.DRIVER)
    merchant = _subject(owner, IdentityType.MERCHANT)
    for operation in (
        lambda: app.courier_detail(wrong_courier, pickup_id=view.pickup.pickup_id),
        lambda: app.courier_detail(wrong_courier, pickup_id=uuid4()),
        lambda: app.merchant_detail(
            merchant, merchant_id=view.pickup.merchant_id, order_id=uuid4()
        ),
    ):
        with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
            operation()


def test_command_and_read_ownership_guards_share_unavailable_classification() -> None:
    view = _view()
    owner = uuid4()
    app = CourierPickupApplication(
        SimpleNamespace(unit_of_work=lambda: _ReadUnit(view, owner))
    )
    wrong_courier = _subject(uuid4(), IdentityType.DRIVER)
    wrong_merchant = _subject(uuid4(), IdentityType.MERCHANT)
    operations = (
        lambda: app.merchant_detail(
            wrong_merchant,
            merchant_id=view.pickup.merchant_id,
            order_id=view.pickup.order_id,
        ),
        lambda: app.courier_command(
            wrong_courier,
            pickup_id=uuid4(),
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key="missing-pickup-command-0001",
            at=NOW,
        ),
        lambda: app.courier_command(
            wrong_courier,
            pickup_id=view.pickup.pickup_id,
            expected_version=view.pickup.version,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key="wrong-courier-command-0001",
            at=NOW,
        ),
    )
    for operation in operations:
        with pytest.raises(CourierPickupConflict, match="^courier_pickup_unavailable$"):
            operation()
