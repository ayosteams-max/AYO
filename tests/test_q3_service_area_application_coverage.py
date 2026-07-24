from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from BACKEND.identity.compatibility_models import AccountLifecycle, IdentityAccount
from BACKEND.persistence.kernel_models import IdempotencyRecord, canonical_request_hash
from BACKEND.persistence.trace import TraceContext
from BACKEND.service_area.application import (
    ConfigureProductAvailability,
    CreateServiceArea,
    EvaluatePickupAvailability,
    RecordBoundary,
    ServiceAreaApplicationService,
)
from BACKEND.service_area.models import (
    AvailabilityOutcome,
    ProductAvailabilityState,
    RideProductCode,
    ServiceArea,
    ServiceAreaGeometry,
    ServiceAreaState,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class _Context(AbstractContextManager[Any]):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def __enter__(self) -> Any:
        return self.unit

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _Service(ServiceAreaApplicationService):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def _uow(self) -> Any:
        return _Context(self.unit)


def _trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def _account() -> IdentityAccount:
    return IdentityAccount(
        subject_id=uuid4(),
        state=AccountLifecycle.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _reservation(
    account_id: UUID, *, completed: bool = False, response: str | None = None
) -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="mobility.service_area.test",
        actor_reference=str(account_id),
        idempotency_key="service-area-command-0001",
        request_hash=canonical_request_hash(b"request"),
        command_id=uuid4(),
        correlation_id=uuid4(),
        request_id=uuid4(),
        response_reference=response,
        created_at=NOW,
        completed_at=NOW if completed else None,
    )


def _unit(account: IdentityAccount) -> Any:
    unit = MagicMock()
    unit.accounts.get_account.return_value = account
    unit.accounts.has_permission.return_value = True
    unit.idempotency.reserve.return_value = _reservation(account.account_id)
    unit.events.append = MagicMock()
    unit.audit.append = MagicMock()
    return unit


def test_service_area_creation_transition_and_replay_are_versioned() -> None:
    account = _account()
    unit = _unit(account)
    unit.service_areas.create.side_effect = lambda value: value
    unit.service_areas.save.side_effect = lambda value, **_: value
    service = _Service(unit)
    area = service.create(
        actor_account_id=account.account_id,
        command=CreateServiceArea(
            internal_name="launch-zone-internal",
            customer_safe_label="AYO service area",
        ),
        idempotency_key="service-area-create-0001",
        trace=_trace(),
        at=NOW,
    )
    assert area.state is ServiceAreaState.PLANNED
    unit.service_areas.get.return_value = area
    approved = service.transition(
        actor_account_id=account.account_id,
        service_area_id=area.service_area_id,
        target=ServiceAreaState.APPROVED,
        expected_version=1,
        idempotency_key="service-area-approve-0001",
        trace=_trace(),
        at=NOW,
    )
    assert approved.state is ServiceAreaState.APPROVED

    with pytest.raises(ValueError, match="administrative command"):
        service.transition(
            actor_account_id=account.account_id,
            service_area_id=area.service_area_id,
            target=ServiceAreaState.PLANNED,
            expected_version=1,
            idempotency_key="service-area-invalid-target",
            trace=_trace(),
            at=NOW,
        )
    unit.service_areas.get.return_value = area
    with pytest.raises(ValueError, match="Stale"):
        service.transition(
            actor_account_id=account.account_id,
            service_area_id=area.service_area_id,
            target=ServiceAreaState.APPROVED,
            expected_version=2,
            idempotency_key="service-area-stale",
            trace=_trace(),
            at=NOW,
        )
    unit.service_areas.get.return_value = approved
    unit.service_areas.current_geometry.return_value = None
    with pytest.raises(ValueError, match="boundary geometry"):
        service.transition(
            actor_account_id=account.account_id,
            service_area_id=area.service_area_id,
            target=ServiceAreaState.ACTIVE,
            expected_version=2,
            idempotency_key="service-area-no-geometry",
            trace=_trace(),
            at=NOW,
        )


def test_boundary_and_product_configuration_publish_evidence_and_fail_closed() -> None:
    account = _account()
    area = ServiceArea(
        service_area_id=uuid4(),
        internal_name="internal-zone",
        state=ServiceAreaState.APPROVED,
        created_at=NOW,
        updated_at=NOW,
    )
    unit = _unit(account)
    unit.service_areas.get.return_value = None
    service = _Service(unit)
    boundary = RecordBoundary(
        boundary_wkt="POLYGON((38 9,39 9,39 10,38 9))",
        provenance="governed-boundary-v1",
    )
    with pytest.raises(LookupError, match="does not exist"):
        service.record_boundary(
            actor_account_id=account.account_id,
            service_area_id=area.service_area_id,
            geometry_version=1,
            command=boundary,
            idempotency_key="boundary-missing-area",
            trace=_trace(),
            at=NOW,
        )
    unit.service_areas.get.return_value = area
    geometry = ServiceAreaGeometry(
        geometry_id=uuid4(),
        service_area_id=area.service_area_id,
        geometry_version=1,
        provenance=boundary.provenance,
        content_hash="a" * 64,
        recorded_at=NOW,
    )
    unit.service_areas.add_geometry.return_value = geometry
    assert (
        service.record_boundary(
            actor_account_id=account.account_id,
            service_area_id=area.service_area_id,
            geometry_version=1,
            command=boundary,
            idempotency_key="boundary-create-0001",
            trace=_trace(),
            at=NOW,
        )
        == geometry
    )

    unit.service_areas.put_availability.side_effect = lambda value, **_: value
    availability = service.configure_product(
        actor_account_id=account.account_id,
        service_area_id=area.service_area_id,
        command=ConfigureProductAvailability(
            product_code=RideProductCode.STANDARD,
            state=ProductAvailabilityState.AVAILABLE,
            effective_from=NOW,
            reason_classification="launch_approved",
            provenance="governed-product-v1",
        ),
        expected_version=None,
        idempotency_key="product-create-0001",
        trace=_trace(),
        at=NOW,
    )
    assert availability.version == 1
    assert unit.events.append.call_args.args[0].event_type == (
        "mobility.product_availability_assigned"
    )


def test_pickup_evaluation_binds_immutable_ride_and_records_outcome() -> None:
    account = _account()
    unit = _unit(account)
    service = _Service(unit)
    ride = MagicMock()
    ride.version = 2
    ride.pickup_reference = "place:addis:bole"
    command = EvaluatePickupAvailability(
        pickup_reference="place:addis:bole",
        longitude=38.75,
        latitude=9.02,
        product_code=RideProductCode.STANDARD,
        intended_service_at=NOW + timedelta(minutes=5),
        ride_request_id=uuid4(),
        ride_request_version=2,
    )
    unit.ride_requests.get_mobility.return_value = None
    with pytest.raises(ValueError, match="missing or stale"):
        service.evaluate_pickup(
            actor_account_id=account.account_id,
            command=command,
            trace=_trace(),
            at=NOW,
        )
    unit.ride_requests.get_mobility.return_value = ride
    with pytest.raises(ValueError, match="immutable Ride Request"):
        service.evaluate_pickup(
            actor_account_id=account.account_id,
            command=command.model_copy(
                update={"pickup_reference": "place:addis:saris"}
            ),
            trace=_trace(),
            at=NOW,
        )
    unit.service_areas.evaluate.return_value = {
        "outcome": AvailabilityOutcome.AVAILABLE,
        "service_area_id": uuid4(),
        "service_area_version": 1,
    }
    unit.service_areas.append_evaluation.side_effect = lambda value: value
    evaluation = service.evaluate_pickup(
        actor_account_id=account.account_id,
        command=command,
        trace=_trace(),
        at=NOW,
    )
    assert evaluation.outcome is AvailabilityOutcome.AVAILABLE
    assert evaluation.ride_request_version == 2
