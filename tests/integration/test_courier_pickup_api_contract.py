from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select, update

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationEnforcer
from BACKEND.config.settings import Settings
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.models import CourierPickupAction
from BACKEND.custody.application import CustodyApplication
from BACKEND.identity.models import IdentityType
from BACKEND.main import (
    CourierPickupPlatformActivation,
    CustodyPlatformActivation,
    create_app,
)
from BACKEND.merchant.models import MerchantKind, OnboardingSource
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.custody_repository import PostgresCustodyRepository
from BACKEND.persistence.tables import (
    commerce_courier_pickup_events,
    commerce_courier_pickup_idempotency,
    commerce_courier_pickups,
    commerce_custody_events,
    commerce_custody_records,
    commerce_order_outbox,
    identity_role_assignments,
    merchant_profiles,
    permissions,
    role_permissions,
)
from tests.integration.test_courier_pickup_idempotency import (
    ACTOR,
    CUSTOMER,
    KEY,
    MERCHANT,
    MERCHANT_OWNER,
    NOW,
    ORDER,
    PERMISSION,
    PICKUP,
    ROLE,
    _cleanup_command_state,
    _effect_counts,
    _seed_command_state,
    _subject,
)

pytestmark = pytest.mark.integration

MERCHANT_READ_PERMISSION = UUID("20000000-0000-4000-8000-000000000021")
MERCHANT_ACK_PERMISSION = UUID("20000000-0000-4000-8000-000000000022")
MERCHANT_ROLE_ASSIGNMENT = UUID("20000000-0000-4000-8000-000000000023")
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
PROHIBITED = {
    "merchant_id",
    "assigned_courier_identity_id",
    "order_id",
    "dispatch_id",
    "assignment_id",
    "actor_identity_id",
    "authority_basis",
    "events",
    "evidence",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "request_hash",
    "location_evidence_reference",
}


class _Resolver:
    def __init__(self, value: AuthorizationSubject) -> None:
        self.value = value

    async def resolve(self, request) -> AuthorizationSubject:
        del request
        return self.value


class _NeverEnforcer:
    def enforce(self, request, requirement) -> None:
        del request, requirement
        raise AssertionError("route-level permission enforcement is prohibited")


def _merchant_subject() -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=MERCHANT_OWNER,
        identity_type=IdentityType.MERCHANT,
        actor_type=ActorType.SERVICE,
    )


def _client(composition, actor: AuthorizationSubject) -> TestClient:
    resolver = _Resolver(actor)
    enforcer = cast(AuthorizationEnforcer, _NeverEnforcer())
    activation = CourierPickupPlatformActivation(
        application=CourierPickupApplication(composition),
        subject_resolver=resolver,
        authorization_enforcer=enforcer,
    )
    return TestClient(
        create_app(
            Settings(
                COURIER_PICKUP_PLATFORM_ENABLED=True,
                CUSTODY_PLATFORM_ENABLED=True,
            ),
            courier_pickup_platform=activation,
            custody_platform=CustodyPlatformActivation(
                application=CustodyApplication(
                    composition, verification_pepper=b"test-custody-pepper" * 2
                ),
                subject_resolver=resolver,
                authorization_enforcer=enforcer,
            ),
        )
    )


@pytest.fixture
def api_contract_state(postgres_engine):
    _cleanup_command_state(postgres_engine)
    _seed_command_state(postgres_engine)
    with postgres_engine.begin() as connection:
        connection.execute(
            update(merchant_profiles)
            .where(merchant_profiles.c.merchant_id == MERCHANT)
            .values(
                kind=MerchantKind.COMPANY.value,
                onboarding_source=OnboardingSource.SELF.value,
            )
        )
        for permission_id, code in (
            (MERCHANT_READ_PERMISSION, "courier_pickup.read_own_merchant"),
            (MERCHANT_ACK_PERMISSION, "courier_pickup.acknowledge_own_merchant"),
        ):
            connection.execute(
                insert(permissions).values(
                    permission_id=permission_id,
                    code=code,
                    description="Courier Pickup public contract evidence.",
                    created_at=NOW,
                )
            )
            connection.execute(
                insert(role_permissions).values(
                    role_id=ROLE, permission_id=permission_id, granted_at=NOW
                )
            )
        connection.execute(
            insert(identity_role_assignments).values(
                assignment_id=MERCHANT_ROLE_ASSIGNMENT,
                identity_id=MERCHANT_OWNER,
                role_id=ROLE,
                assigned_by_identity_id=ACTOR,
                assigned_at=NOW,
            )
        )
    try:
        yield
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(identity_role_assignments).where(
                    identity_role_assignments.c.assignment_id
                    == MERCHANT_ROLE_ASSIGNMENT
                )
            )
            connection.execute(
                delete(role_permissions).where(
                    role_permissions.c.permission_id.in_(
                        (MERCHANT_READ_PERMISSION, MERCHANT_ACK_PERMISSION)
                    )
                )
            )
            connection.execute(
                delete(permissions).where(
                    permissions.c.permission_id.in_(
                        (MERCHANT_READ_PERMISSION, MERCHANT_ACK_PERMISSION)
                    )
                )
            )
        _cleanup_command_state(postgres_engine)


def _assert_public(response, fields) -> None:
    assert response.status_code == 200
    assert set(response.json()) == fields
    assert not PROHIBITED.intersection(response.json())


@pytest.mark.usefixtures("api_contract_state")
def test_postgres_composed_http_exposes_exact_caller_contracts(
    postgres_engine,
    postgres_composition,
) -> None:
    courier = _client(postgres_composition, _subject())
    courier_status = courier.get(f"/api/mobile/courier-pickups/{PICKUP}")
    courier_start = courier.post(
        f"/api/mobile/courier-pickups/{PICKUP}/actions",
        headers={"Idempotency-Key": KEY},
        json={"expected_version": 1, "action": "start_travel"},
    )
    courier_arrive = courier.post(
        f"/api/mobile/courier-pickups/{PICKUP}/actions",
        headers={"Idempotency-Key": "postgres-arrival-contract-0001"},
        json={"expected_version": 2, "action": "mark_arrived"},
    )
    merchant = _client(postgres_composition, _merchant_subject())
    merchant_status = merchant.get(
        f"/api/mobile/merchants/{MERCHANT}/orders/{ORDER}/courier-pickup"
    )
    merchant_command = merchant.post(
        f"/api/mobile/merchants/{MERCHANT}/courier-pickups/{PICKUP}/acknowledge",
        headers={"Idempotency-Key": "postgres-merchant-contract-0001"},
        json={"expected_version": 3, "action": "acknowledge_arrival"},
    )
    for response in (courier_status, courier_start, courier_arrive):
        _assert_public(response, COURIER_FIELDS)
    for response in (merchant_status, merchant_command):
        _assert_public(response, MERCHANT_FIELDS)
    replay = merchant.post(
        f"/api/mobile/merchants/{MERCHANT}/courier-pickups/{PICKUP}/acknowledge",
        headers={"Idempotency-Key": "postgres-merchant-contract-0001"},
        json={"expected_version": 3, "action": "acknowledge_arrival"},
    )
    assert replay.content == merchant_command.content
    with postgres_engine.connect() as connection:
        custody = (
            connection.execute(
                select(commerce_custody_records).where(
                    commerce_custody_records.c.pickup_id == PICKUP
                )
            )
            .mappings()
            .one()
        )
        assert custody["order_id"] == ORDER
        assert custody["merchant_id"] == MERCHANT
        assert custody["courier_identity_id"] == ACTOR
        assert custody["state"] == "waiting_for_pickup"
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_custody_events)
                .where(commerce_custody_events.c.custody_id == custody["custody_id"])
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_order_outbox)
                .where(
                    commerce_order_outbox.c.order_id == ORDER,
                    commerce_order_outbox.c.event_type == "commerce.custody.activated",
                )
            ).scalar_one()
            == 1
        )


@pytest.mark.usefixtures("api_contract_state")
def test_custody_activation_failure_rolls_back_merchant_acknowledgement(
    postgres_engine,
    postgres_composition,
) -> None:
    courier = CourierPickupApplication(postgres_composition)
    travelling = courier.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key="rollback-travel-0001",
        at=NOW,
    )
    arrived = courier.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=travelling.pickup.version,
        action=CourierPickupAction.MARK_ARRIVED,
        idempotency_key="rollback-arrival-0001",
        at=NOW,
    )

    class FailingCustodyRepository(PostgresCustodyRepository):
        def activate(self, *, pickup_id, actor_identity_id, at):
            super().activate(
                pickup_id=pickup_id,
                actor_identity_id=actor_identity_id,
                at=at,
            )
            raise RuntimeError("forced custody activation failure")

    failing = PostgresRepositoryComposition(postgres_engine)
    failing._factories["custody"] = FailingCustodyRepository
    with pytest.raises(RuntimeError, match="forced custody activation failure"):
        CourierPickupApplication(failing).merchant_acknowledge(
            _merchant_subject(),
            merchant_id=MERCHANT,
            pickup_id=PICKUP,
            expected_version=arrived.pickup.version,
            idempotency_key="rollback-merchant-ack-0001",
            at=NOW,
        )
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(commerce_courier_pickups.c.state).where(
                    commerce_courier_pickups.c.pickup_id == PICKUP
                )
            ).scalar_one()
            == "arrived_at_merchant"
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_custody_records)
                .where(commerce_custody_records.c.pickup_id == PICKUP)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_courier_pickup_events)
                .where(
                    commerce_courier_pickup_events.c.pickup_id == PICKUP,
                    commerce_courier_pickup_events.c.event_type
                    == "commerce.courier_pickup.merchant_acknowledged",
                )
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_order_outbox)
                .where(
                    commerce_order_outbox.c.order_id == ORDER,
                    commerce_order_outbox.c.event_type == "commerce.custody.activated",
                )
            ).scalar_one()
            == 0
        )


@pytest.mark.usefixtures("api_contract_state")
@pytest.mark.parametrize("custody_state", ["missing", "mismatched"])
def test_completed_acknowledgement_replay_never_repairs_custody(
    postgres_engine,
    postgres_composition,
    custody_state,
) -> None:
    courier = CourierPickupApplication(postgres_composition)
    travelling = courier.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key="replay-integrity-travel-0001",
        at=NOW,
    )
    arrived = courier.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=travelling.pickup.version,
        action=CourierPickupAction.MARK_ARRIVED,
        idempotency_key="replay-integrity-arrival-0001",
        at=NOW,
    )
    merchant = _client(postgres_composition, _merchant_subject())
    path = f"/api/mobile/merchants/{MERCHANT}/courier-pickups/{PICKUP}/acknowledge"
    headers = {"Idempotency-Key": "replay-integrity-merchant-0001"}
    body = {
        "expected_version": arrived.pickup.version,
        "action": "acknowledge_arrival",
    }
    assert merchant.post(path, headers=headers, json=body).status_code == 200

    with postgres_engine.begin() as connection:
        custody_id = connection.execute(
            select(commerce_custody_records.c.custody_id).where(
                commerce_custody_records.c.pickup_id == PICKUP
            )
        ).scalar_one()
        if custody_state == "missing":
            connection.execute(
                delete(commerce_custody_events).where(
                    commerce_custody_events.c.custody_id == custody_id
                )
            )
            connection.execute(
                delete(commerce_order_outbox).where(
                    commerce_order_outbox.c.order_id == ORDER,
                    commerce_order_outbox.c.event_type == "commerce.custody.activated",
                )
            )
            connection.execute(
                delete(commerce_custody_records).where(
                    commerce_custody_records.c.custody_id == custody_id
                )
            )
        else:
            connection.execute(
                update(commerce_custody_records)
                .where(commerce_custody_records.c.custody_id == custody_id)
                .values(courier_identity_id=CUSTOMER)
            )
        before_pickup = connection.execute(
            select(
                commerce_courier_pickups.c.state,
                commerce_courier_pickups.c.version,
            ).where(commerce_courier_pickups.c.pickup_id == PICKUP)
        ).one()
        before_idempotency = tuple(
            connection.execute(
                select(commerce_courier_pickup_idempotency).where(
                    commerce_courier_pickup_idempotency.c.pickup_id == PICKUP
                )
            ).mappings()
        )
        before_events = connection.execute(
            select(func.count())
            .select_from(commerce_custody_events)
            .where(commerce_custody_events.c.custody_id == custody_id)
        ).scalar_one()
        before_outbox = connection.execute(
            select(func.count())
            .select_from(commerce_order_outbox)
            .where(
                commerce_order_outbox.c.order_id == ORDER,
                commerce_order_outbox.c.event_type == "commerce.custody.activated",
            )
        ).scalar_one()

    replay = merchant.post(path, headers=headers, json=body)
    assert replay.status_code == 409
    assert replay.json() == {
        "error": {"code": "courier_pickup_temporarily_unavailable"}
    }
    with postgres_engine.connect() as connection:
        custody_rows = (
            connection.execute(
                select(commerce_custody_records).where(
                    commerce_custody_records.c.pickup_id == PICKUP
                )
            )
            .mappings()
            .all()
        )
        assert len(custody_rows) == (0 if custody_state == "missing" else 1)
        if custody_rows:
            assert custody_rows[0]["courier_identity_id"] == CUSTOMER
        assert (
            connection.execute(
                select(
                    commerce_courier_pickups.c.state,
                    commerce_courier_pickups.c.version,
                ).where(commerce_courier_pickups.c.pickup_id == PICKUP)
            ).one()
            == before_pickup
        )
        assert (
            tuple(
                connection.execute(
                    select(commerce_courier_pickup_idempotency).where(
                        commerce_courier_pickup_idempotency.c.pickup_id == PICKUP
                    )
                ).mappings()
            )
            == before_idempotency
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_custody_events)
                .where(commerce_custody_events.c.custody_id == custody_id)
            ).scalar_one()
            == before_events
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_order_outbox)
                .where(
                    commerce_order_outbox.c.order_id == ORDER,
                    commerce_order_outbox.c.event_type == "commerce.custody.activated",
                )
            ).scalar_one()
            == before_outbox
        )


@pytest.mark.usefixtures("api_contract_state")
def test_concurrent_merchant_acknowledgements_create_one_custody(
    postgres_engine,
    postgres_composition,
) -> None:
    courier = CourierPickupApplication(postgres_composition)
    travelling = courier.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key="concurrent-ack-travel-0001",
        at=NOW,
    )
    arrived = courier.courier_command(
        _subject(),
        pickup_id=PICKUP,
        expected_version=travelling.pickup.version,
        action=CourierPickupAction.MARK_ARRIVED,
        idempotency_key="concurrent-ack-arrival-0001",
        at=NOW,
    )
    barrier = Barrier(2)

    def acknowledge():
        barrier.wait(timeout=10)
        return CourierPickupApplication(
            PostgresRepositoryComposition(postgres_engine)
        ).merchant_acknowledge(
            _merchant_subject(),
            merchant_id=MERCHANT,
            pickup_id=PICKUP,
            expected_version=arrived.pickup.version,
            idempotency_key="concurrent-merchant-ack-0001",
            at=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: acknowledge(), range(2)))
    assert results[0] == results[1]
    assert results[0].pickup.state.value == "waiting_for_pickup"
    with postgres_engine.connect() as connection:
        custody_id = connection.execute(
            select(commerce_custody_records.c.custody_id).where(
                commerce_custody_records.c.pickup_id == PICKUP,
                commerce_custody_records.c.order_id == ORDER,
                commerce_custody_records.c.merchant_id == MERCHANT,
                commerce_custody_records.c.courier_identity_id == ACTOR,
            )
        ).scalar_one()
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_courier_pickup_events)
                .where(
                    commerce_courier_pickup_events.c.pickup_id == PICKUP,
                    commerce_courier_pickup_events.c.event_type
                    == "commerce.courier_pickup.merchant_acknowledged",
                )
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_custody_records)
                .where(commerce_custody_records.c.pickup_id == PICKUP)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_custody_events)
                .where(
                    commerce_custody_events.c.custody_id == custody_id,
                    commerce_custody_events.c.event_type
                    == "commerce.custody.activated",
                )
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(commerce_order_outbox)
                .where(
                    commerce_order_outbox.c.order_id == ORDER,
                    commerce_order_outbox.c.event_type == "commerce.custody.activated",
                )
            ).scalar_one()
            == 1
        )


@pytest.mark.usefixtures("api_contract_state")
def test_postgres_http_replay_is_byte_equivalent_without_duplicate_effects(
    postgres_engine,
    postgres_composition,
) -> None:
    body = {"expected_version": 1, "action": "start_travel"}
    first = _client(postgres_composition, _subject()).post(
        f"/api/mobile/courier-pickups/{PICKUP}/actions",
        headers={"Idempotency-Key": KEY},
        json=body,
    )
    before = _effect_counts(postgres_engine)
    replay = _client(PostgresRepositoryComposition(postgres_engine), _subject()).post(
        f"/api/mobile/courier-pickups/{PICKUP}/actions",
        headers={"Idempotency-Key": KEY},
        json=body,
    )
    assert first.status_code == replay.status_code == 200
    assert first.content == replay.content
    assert set(replay.json()) == COURIER_FIELDS
    assert _effect_counts(postgres_engine) == before == (1, 1, 1, 1, 1)


@pytest.mark.usefixtures("api_contract_state")
def test_postgres_http_non_enumeration_and_permission_denial_are_distinct(
    postgres_engine,
    postgres_composition,
) -> None:
    wrong = _subject().model_copy(update={"identity_id": uuid4()})
    wrong_client = _client(postgres_composition, wrong)
    unavailable = [
        wrong_client.get(f"/api/mobile/courier-pickups/{PICKUP}"),
        wrong_client.get(f"/api/mobile/courier-pickups/{uuid4()}"),
    ]
    assert [response.status_code for response in unavailable] == [404, 404]
    assert [response.json() for response in unavailable] == [
        {"error": {"code": "courier_pickup_unavailable"}},
        {"error": {"code": "courier_pickup_unavailable"}},
    ]

    with postgres_engine.begin() as connection:
        connection.execute(
            delete(role_permissions).where(
                role_permissions.c.role_id == ROLE,
                role_permissions.c.permission_id == PERMISSION,
            )
        )
    denied = _client(PostgresRepositoryComposition(postgres_engine), _subject()).get(
        f"/api/mobile/courier-pickups/{PICKUP}"
    )
    assert denied.status_code == 403
    assert denied.json() == {"error": {"code": "access_denied"}}
    assert _effect_counts(postgres_engine) == (0, 0, 0, 0, 0)
