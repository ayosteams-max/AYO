from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_pickup.application import CourierPickupApplication
from BACKEND.courier_pickup.engine import CourierPickupConflict
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupRecord,
    CourierPickupState,
    CourierPickupView,
)
from BACKEND.custody.models import CustodyState
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import MerchantState

NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)


def subject(identity_id: UUID, identity_type: IdentityType) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=identity_type,
        actor_type=(
            ActorType.DRIVER
            if identity_type is IdentityType.DRIVER
            else ActorType.SERVICE
        ),
    )


def pickup(courier_id: UUID, merchant_id: UUID) -> CourierPickupRecord:
    return CourierPickupRecord(
        pickup_id=uuid4(),
        dispatch_id=uuid4(),
        assignment_id=uuid4(),
        assignment_version=1,
        attempt_number=1,
        order_id=uuid4(),
        merchant_id=merchant_id,
        assigned_courier_identity_id=courier_id,
        assignment_message_id=uuid4(),
        policy_code="AYO_COURIER_PICKUP_POLICY_V1",
        policy_version=1,
        state=CourierPickupState.ASSIGNED,
        version=1,
        assigned_at=NOW,
        travelling_at=None,
        arrived_at=None,
        merchant_acknowledged_at=None,
        waiting_duration_seconds=None,
        terminal_reason=None,
        custody_accepted_at=None,
        updated_at=NOW,
    )


class FakePickupRepository:
    def __init__(self, value: CourierPickupRecord) -> None:
        self.value = value
        self.replays: dict[tuple[UUID, str, str], CourierPickupView] = {}

    def get(self, pickup_id, *, lock=False):
        del lock
        return self.value if pickup_id == self.value.pickup_id else None

    def view(self, pickup_id):
        return self._view() if pickup_id == self.value.pickup_id else None

    def reserve(self, *, actor_id, pickup_id, key, action, **kwargs):
        del kwargs
        token = (actor_id, action.value, key)
        existing = self.replays.get(token)
        if existing is not None and existing.pickup.pickup_id != pickup_id:
            raise CourierPickupConflict("idempotency_conflict")
        return existing

    def transition(self, current, *, target, action, actor_id, key, at, **kwargs):
        del kwargs
        updates = {"state": target, "version": current.version + 1, "updated_at": at}
        if action is CourierPickupAction.START_TRAVEL:
            updates["travelling_at"] = at
        elif action is CourierPickupAction.MARK_ARRIVED:
            updates["arrived_at"] = at
        elif action is CourierPickupAction.CORRECT_ARRIVAL:
            updates["arrived_at"] = None
        elif action is CourierPickupAction.ACKNOWLEDGE_ARRIVAL:
            updates["merchant_acknowledged_at"] = at
            updates["waiting_duration_seconds"] = int(
                (at - current.arrived_at).total_seconds()
            )
        elif action is CourierPickupAction.CORRECT_WAITING:
            updates["merchant_acknowledged_at"] = None
            updates["waiting_duration_seconds"] = None
        self.value = current.model_copy(update=updates)
        result = self._view()
        self.replays[(actor_id, action.value, key)] = result
        return result

    def _view(self) -> CourierPickupView:
        return CourierPickupView(pickup=self.value, events=(), evidence=())


class FakeUnit:
    def __init__(
        self,
        repository: FakePickupRepository,
        *,
        merchant_owner: UUID,
        permissions: set[str],
        custody_accepted: bool = False,
    ) -> None:
        self.courier_pickup = repository
        self.authorization = SimpleNamespace(
            has_permission=lambda identity_id, permission, at: permission in permissions
        )
        self.merchants = SimpleNamespace(
            get_profile=lambda merchant_id, lock=False: SimpleNamespace(
                merchant_id=merchant_id,
                owner_identity_id=merchant_owner,
                state=MerchantState.APPROVED,
            )
        )
        self.custody = SimpleNamespace(
            get_by_order=lambda order_id: (
                SimpleNamespace(custody=SimpleNamespace(state=CustodyState.ACCEPTED))
                if custody_accepted
                else None
            )
        )
        self.audit_events: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeComposition:
    def __init__(self, unit: FakeUnit) -> None:
        self.unit = unit

    def unit_of_work(self):
        return self.unit


def application(
    *,
    permissions: set[str],
    custody_accepted: bool = False,
) -> tuple[CourierPickupApplication, CourierPickupRecord, UUID, UUID]:
    courier_id, merchant_id, merchant_owner = uuid4(), uuid4(), uuid4()
    value = pickup(courier_id, merchant_id)
    unit = FakeUnit(
        FakePickupRepository(value),
        merchant_owner=merchant_owner,
        permissions=permissions,
        custody_accepted=custody_accepted,
    )
    return (
        CourierPickupApplication(FakeComposition(unit)),
        value,
        courier_id,
        merchant_owner,
    )


def test_authorized_courier_progress_and_false_arrival_correction() -> None:
    app, value, courier_id, _ = application(
        permissions={
            "courier_pickup.manage_assigned",
            "courier_pickup.correct_assigned",
        }
    )
    actor = subject(courier_id, IdentityType.DRIVER)
    travelling = app.courier_command(
        actor,
        pickup_id=value.pickup_id,
        expected_version=1,
        action=CourierPickupAction.START_TRAVEL,
        idempotency_key="travel-action-0001",
        at=NOW + timedelta(minutes=1),
    )
    arrived = app.courier_command(
        actor,
        pickup_id=value.pickup_id,
        expected_version=travelling.pickup.version,
        action=CourierPickupAction.MARK_ARRIVED,
        idempotency_key="arrival-action-0001",
        at=NOW + timedelta(minutes=2),
        location_evidence_reference=uuid4(),
        location_evidence_version=3,
        location_evidence_observed_at=NOW + timedelta(minutes=1, seconds=30),
    )
    corrected = app.courier_command(
        actor,
        pickup_id=value.pickup_id,
        expected_version=arrived.pickup.version,
        action=CourierPickupAction.CORRECT_ARRIVAL,
        idempotency_key="arrival-correction-0001",
        at=NOW + timedelta(minutes=3),
    )
    assert corrected.pickup.state is CourierPickupState.TRAVELLING
    assert corrected.pickup.arrived_at is None


def test_permission_and_custody_boundaries_fail_closed() -> None:
    app, value, courier_id, _ = application(permissions=set())
    with pytest.raises(CourierPickupConflict, match="access_denied"):
        app.courier_command(
            subject(courier_id, IdentityType.DRIVER),
            pickup_id=value.pickup_id,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key="travel-action-0002",
            at=NOW,
        )

    app, value, courier_id, _ = application(
        permissions={"courier_pickup.manage_assigned"}, custody_accepted=True
    )
    with pytest.raises(CourierPickupConflict, match="authority_ended_at_custody"):
        app.courier_command(
            subject(courier_id, IdentityType.DRIVER),
            pickup_id=value.pickup_id,
            expected_version=1,
            action=CourierPickupAction.START_TRAVEL,
            idempotency_key="travel-action-0003",
            at=NOW,
        )


def test_stale_location_and_wrong_merchant_scope_are_rejected() -> None:
    app, value, courier_id, merchant_owner = application(
        permissions={
            "courier_pickup.manage_assigned",
            "courier_pickup.acknowledge_own_merchant",
        }
    )
    with pytest.raises(CourierPickupConflict, match="location_evidence_stale"):
        app.courier_command(
            subject(courier_id, IdentityType.DRIVER),
            pickup_id=value.pickup_id,
            expected_version=1,
            action=CourierPickupAction.MARK_ARRIVED,
            idempotency_key="arrival-action-0002",
            at=NOW,
            location_evidence_reference=uuid4(),
            location_evidence_version=1,
            location_evidence_observed_at=NOW - timedelta(minutes=6),
        )
    with pytest.raises(CourierPickupConflict, match="access_denied"):
        app.merchant_acknowledge(
            subject(merchant_owner, IdentityType.MERCHANT),
            merchant_id=uuid4(),
            pickup_id=value.pickup_id,
            expected_version=1,
            idempotency_key="merchant-ack-0001",
            at=NOW,
        )
