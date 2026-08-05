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
from BACKEND.ride_request.mobility_application import (
    CreatePassengerMobilityRideRequest,
    PassengerMobilityRideRequestService,
    RideRequestAuthorizationError,
)
from BACKEND.ride_request.models import (
    MobilityRideRequestState,
    PassengerMobilityRideRequest,
    ScheduleIntentType,
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


class _Service(PassengerMobilityRideRequestService):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def _uow(self) -> Any:
        return _Context(self.unit)


def _trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def _account(subject_id: UUID | None = None) -> IdentityAccount:
    return IdentityAccount(
        subject_id=subject_id or uuid4(),
        state=AccountLifecycle.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _reservation(
    account_id: UUID,
    *,
    completed: bool = False,
    response: str | None = None,
) -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="mobility.ride_request.test",
        actor_reference=str(account_id),
        idempotency_key="mobility-command-0001",
        request_hash=canonical_request_hash(b"request"),
        command_id=uuid4(),
        correlation_id=uuid4(),
        request_id=uuid4(),
        response_reference=response,
        created_at=NOW,
        completed_at=NOW if completed else None,
    )


def _ride(
    subject_id: UUID,
    *,
    state: MobilityRideRequestState = MobilityRideRequestState.DRAFT,
    version: int = 1,
    expires_at: datetime = NOW + timedelta(hours=1),
) -> PassengerMobilityRideRequest:
    return PassengerMobilityRideRequest(
        client_request_id=uuid4(),
        requester_subject_id=subject_id,
        passenger_subject_id=subject_id,
        state=state,
        pickup_reference="place:addis:bole",
        destination_reference="place:addis:saris",
        schedule_intent=ScheduleIntentType.IMMEDIATE,
        passenger_count=1,
        version=version,
        created_at=NOW,
        updated_at=NOW,
        expires_at=expires_at,
    )


def _unit(account: IdentityAccount) -> Any:
    unit = MagicMock()
    unit.accounts.get_account.return_value = account
    unit.accounts.has_permission.return_value = False
    unit.profiles.active_relationship_between.return_value = object()
    unit.idempotency.reserve.return_value = _reservation(account.account_id)
    unit.ride_requests.create_mobility.side_effect = lambda value: value
    unit.ride_requests.save_mobility.side_effect = lambda value, **_: value
    unit.events.append = MagicMock()
    unit.audit.append = MagicMock()
    return unit


def test_create_draft_reuses_account_household_idempotency_and_evidence() -> None:
    account = _account()
    passenger = uuid4()
    unit = _unit(account)
    service = _Service(unit)
    command = CreatePassengerMobilityRideRequest(
        client_request_id=uuid4(),
        passenger_subject_id=passenger,
        pickup_reference="place:addis:bole",
        destination_reference="place:addis:saris",
        schedule_intent=ScheduleIntentType.IMMEDIATE,
        passenger_count=2,
        expires_at=NOW + timedelta(hours=1),
    )
    created = service.create_draft(
        actor_account_id=account.account_id,
        command=command,
        idempotency_key="mobility-create-0001",
        trace=_trace(),
        at=NOW,
    )
    assert created.requester_subject_id == account.subject_id
    assert created.passenger_subject_id == passenger
    assert unit.events.append.call_args.args[0].event_type == (
        "mobility.ride_request_created"
    )
    assert unit.audit.append.call_args.args[0].safe_metadata["state_to"] == "draft"

    unit.idempotency.reserve.return_value = _reservation(
        account.account_id,
        completed=True,
        response=f"mobility_ride_request/{created.request_id}",
    )
    unit.ride_requests.get_mobility.return_value = created
    assert (
        service.create_draft(
            actor_account_id=account.account_id,
            command=command,
            idempotency_key="mobility-create-0001",
            trace=_trace(),
            at=NOW,
        )
        == created
    )


def test_create_and_transition_fail_closed_for_authority_missing_and_stale_state() -> (
    None
):
    account = _account()
    unit = _unit(account)
    service = _Service(unit)
    unit.profiles.active_relationship_between.return_value = None
    with pytest.raises(RideRequestAuthorizationError, match="trusted household"):
        service.create_draft(
            actor_account_id=account.account_id,
            command=CreatePassengerMobilityRideRequest(
                client_request_id=uuid4(),
                passenger_subject_id=uuid4(),
                pickup_reference="place:addis:bole",
                destination_reference="place:addis:saris",
                schedule_intent=ScheduleIntentType.IMMEDIATE,
                passenger_count=1,
                expires_at=NOW + timedelta(hours=1),
            ),
            idempotency_key="mobility-create-denied",
            trace=_trace(),
            at=NOW,
        )

    ride = _ride(account.subject_id)
    unit.ride_requests.get_mobility.return_value = None
    with pytest.raises(LookupError, match="does not exist"):
        service.validate(
            actor_account_id=account.account_id,
            request_id=ride.request_id,
            expected_version=1,
            idempotency_key="mobility-validate-missing",
            trace=_trace(),
            at=NOW,
        )
    unit.ride_requests.get_mobility.return_value = ride
    with pytest.raises(ValueError, match="Stale"):
        service.validate(
            actor_account_id=account.account_id,
            request_id=ride.request_id,
            expected_version=2,
            idempotency_key="mobility-validate-stale",
            trace=_trace(),
            at=NOW,
        )
    other = _account()
    unit.accounts.get_account.return_value = other
    with pytest.raises(RideRequestAuthorizationError, match="Only requester"):
        service.validate(
            actor_account_id=other.account_id,
            request_id=ride.request_id,
            expected_version=1,
            idempotency_key="mobility-validate-cross-account",
            trace=_trace(),
            at=NOW,
        )


def test_lifecycle_transitions_publish_events_and_reject_invalid_transition() -> None:
    account = _account()
    unit = _unit(account)
    service = _Service(unit)
    draft = _ride(account.subject_id)
    unit.ride_requests.get_mobility.return_value = draft
    validated = service.validate(
        actor_account_id=account.account_id,
        request_id=draft.request_id,
        expected_version=1,
        idempotency_key="mobility-validate-0001",
        trace=_trace(),
        at=NOW,
    )
    assert validated.state is MobilityRideRequestState.VALIDATED

    unit.ride_requests.get_mobility.return_value = validated
    submitted = service.submit(
        actor_account_id=account.account_id,
        request_id=draft.request_id,
        expected_version=2,
        idempotency_key="mobility-submit-0001",
        trace=_trace(),
        at=NOW,
    )
    assert submitted.state is MobilityRideRequestState.SUBMITTED

    unit.ride_requests.get_mobility.return_value = submitted
    withdrawn = service.withdraw(
        actor_account_id=account.account_id,
        request_id=draft.request_id,
        expected_version=3,
        idempotency_key="mobility-withdraw-0001",
        trace=_trace(),
        at=NOW,
    )
    assert withdrawn.state is MobilityRideRequestState.WITHDRAWN
    unit.ride_requests.get_mobility.return_value = withdrawn
    with pytest.raises(ValueError, match="Invalid Passenger Mobility"):
        service.submit(
            actor_account_id=account.account_id,
            request_id=draft.request_id,
            expected_version=4,
            idempotency_key="mobility-submit-terminal",
            trace=_trace(),
            at=NOW,
        )


def test_expiry_and_authorized_reads_preserve_terminal_and_tenant_boundaries() -> None:
    account = _account()
    unit = _unit(account)
    service = _Service(unit)
    ride = _ride(account.subject_id, expires_at=NOW + timedelta(minutes=5))
    unit.ride_requests.get_mobility.return_value = ride
    with pytest.raises(ValueError, match="not reached expiry"):
        service.expire(
            actor_account_id=account.account_id,
            request_id=ride.request_id,
            expected_version=1,
            idempotency_key="mobility-expire-early",
            trace=_trace(),
            at=NOW,
        )
    expired_source = ride.model_copy(update={"expires_at": NOW})
    unit.ride_requests.get_mobility.return_value = expired_source
    expired = service.expire(
        actor_account_id=account.account_id,
        request_id=ride.request_id,
        expected_version=1,
        idempotency_key="mobility-expire-0001",
        trace=_trace(),
        at=NOW,
    )
    assert expired.state is MobilityRideRequestState.EXPIRED

    unit.ride_requests.get_mobility.return_value = ride
    assert (
        service.get_authorized(
            actor_account_id=account.account_id, request_id=ride.request_id, at=NOW
        )
        == ride
    )
    other = _account()
    unit.accounts.get_account.return_value = other
    with pytest.raises(RideRequestAuthorizationError, match="access denied"):
        service.get_authorized(
            actor_account_id=other.account_id, request_id=ride.request_id, at=NOW
        )
    unit.accounts.has_permission.return_value = True
    assert (
        service.get_authorized(
            actor_account_id=other.account_id,
            request_id=ride.request_id,
            administrative_override=True,
            at=NOW,
        )
        == ride
    )
