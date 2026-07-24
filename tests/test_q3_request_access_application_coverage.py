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
from BACKEND.request_access.application import (
    DeclareChannelCapability,
    RegisterSourceAdapter,
    RequestAccessApplicationService,
    RequestAccessAuthorizationError,
)
from BACKEND.request_access.models import (
    AccessChannel,
    CapabilityState,
    ChannelActionCapability,
    InteractionMethod,
    InteractionProvenanceEnvelope,
    ProvenancePurpose,
    SourceAdapter,
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


class _Service(RequestAccessApplicationService):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def _uow(self) -> Any:
        return _Context(self.unit)


def _trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def _account() -> IdentityAccount:
    return IdentityAccount(
        account_id=uuid4(),
        subject_id=uuid4(),
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
        scope="access.provenance.test",
        actor_reference=str(account_id),
        idempotency_key="request-access-idempotency-0001",
        request_hash=canonical_request_hash(b"request"),
        command_id=uuid4(),
        correlation_id=uuid4(),
        request_id=uuid4(),
        response_reference=response,
        created_at=NOW,
        completed_at=NOW if completed else None,
    )


def _adapter(*, active: bool = True) -> SourceAdapter:
    return SourceAdapter(
        adapter_id=uuid4(),
        adapter_code="ayo.mobile.reference",
        adapter_version=1,
        channel=AccessChannel.MOBILE_APP,
        active=active,
        created_at=NOW,
    )


def _capability(
    adapter: SourceAdapter,
    *,
    state: CapabilityState = CapabilityState.SUPPORTED,
    version: int = 1,
) -> ChannelActionCapability:
    return ChannelActionCapability(
        capability_id=uuid4(),
        target_domain="mobility",
        command_type="mobility.ride_request.create",
        channel=adapter.channel,
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        state=state,
        effective_from=NOW - timedelta(minutes=1),
        version=version,
        created_at=NOW,
        updated_at=NOW,
    )


def _unit(account: IdentityAccount) -> Any:
    unit = MagicMock()
    unit.accounts.get_account.return_value = account
    unit.accounts.has_permission.return_value = True
    unit.idempotency.reserve.return_value = _reservation(account.account_id)
    unit.events.append = MagicMock()
    unit.audit.append = MagicMock()
    return unit


def _envelope(
    account: IdentityAccount,
    adapter: SourceAdapter,
    *,
    purpose: ProvenancePurpose = ProvenancePurpose.INITIATION,
    acting_subject_id: UUID | None = None,
    continuity_reference: str | None = None,
) -> InteractionProvenanceEnvelope:
    return InteractionProvenanceEnvelope(
        purpose=purpose,
        target_domain="mobility",
        target_type="mobility.ride_request",
        target_id="ride-request-0001",
        target_version=1,
        command_type="mobility.ride_request.create",
        channel=adapter.channel,
        interaction_method=InteractionMethod.SELF_SERVICE,
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        authenticated_account_id=account.account_id,
        authenticated_subject_id=account.subject_id,
        acting_subject_id=acting_subject_id or account.subject_id,
        requester_subject_id=account.subject_id,
        passenger_subject_id=account.subject_id,
        continuity_reference=continuity_reference,
    )


def test_adapter_registration_records_evidence_and_replays() -> None:
    account = _account()
    unit = _unit(account)
    unit.request_access.register_adapter.side_effect = lambda value: value
    service = _Service(unit)
    command = RegisterSourceAdapter(
        adapter_code="ayo.mobile.reference",
        adapter_version=1,
        channel=AccessChannel.MOBILE_APP,
    )
    created = service.register_adapter(
        actor_account_id=account.account_id,
        command=command,
        idempotency_key="adapter-register-0001",
        trace=_trace(),
        at=NOW,
    )
    assert created.active
    assert unit.events.append.call_args.args[0].event_type == (
        "access.source_adapter_registered"
    )
    unit.idempotency.reserve.return_value = _reservation(
        account.account_id,
        completed=True,
        response=f"request_access_adapter/{created.adapter_id}",
    )
    unit.request_access.get_adapter.return_value = created
    assert (
        service.register_adapter(
            actor_account_id=account.account_id,
            command=command,
            idempotency_key="adapter-register-0001",
            trace=_trace(),
            at=NOW,
        )
        == created
    )
    unit.request_access.get_adapter.return_value = None
    with pytest.raises(RuntimeError, match="adapter result"):
        service.register_adapter(
            actor_account_id=account.account_id,
            command=command,
            idempotency_key="adapter-register-0001",
            trace=_trace(),
            at=NOW,
        )


def test_capability_requires_active_adapter_and_optimistic_version() -> None:
    account, adapter = _account(), _adapter()
    unit = _unit(account)
    service = _Service(unit)
    command = DeclareChannelCapability(
        target_domain="mobility",
        command_type="mobility.ride_request.create",
        adapter_id=adapter.adapter_id,
        state=CapabilityState.SUPPORTED,
        effective_from=NOW,
    )
    unit.request_access.get_adapter.return_value = None
    with pytest.raises(ValueError, match="Active registered"):
        service.declare_capability(
            actor_account_id=account.account_id,
            command=command,
            expected_version=None,
            idempotency_key="capability-create-0001",
            trace=_trace(),
            at=NOW,
        )
    unit.request_access.get_adapter.return_value = adapter
    existing = _capability(adapter)
    unit.request_access.get_capability.return_value = existing
    with pytest.raises(ValueError, match="already exists"):
        service.declare_capability(
            actor_account_id=account.account_id,
            command=command,
            expected_version=None,
            idempotency_key="capability-create-0002",
            trace=_trace(),
            at=NOW,
        )
    unit.request_access.get_capability.return_value = None
    with pytest.raises(ValueError, match="Stale or missing"):
        service.declare_capability(
            actor_account_id=account.account_id,
            command=command,
            expected_version=1,
            idempotency_key="capability-update-0001",
            trace=_trace(),
            at=NOW,
        )
    unit.request_access.get_capability.return_value = existing
    with pytest.raises(ValueError, match="Stale or missing"):
        service.declare_capability(
            actor_account_id=account.account_id,
            command=command,
            expected_version=2,
            idempotency_key="capability-update-0002",
            trace=_trace(),
            at=NOW,
        )
    unit.request_access.put_capability.side_effect = lambda value, **_: value
    updated = service.declare_capability(
        actor_account_id=account.account_id,
        command=command.model_copy(update={"state": CapabilityState.RETIRED}),
        expected_version=1,
        idempotency_key="capability-update-0003",
        trace=_trace(),
        at=NOW,
    )
    assert updated.version == 2
    assert unit.events.append.call_args.args[0].event_type == (
        "access.channel_capability_retired"
    )


def test_continuity_issue_validates_lifetime_actor_and_replay() -> None:
    account = _account()
    unit = _unit(account)
    service = _Service(unit)
    with pytest.raises(ValueError, match="lifetime"):
        service.issue_continuity_reference(
            actor_account_id=account.account_id,
            acting_subject_id=account.subject_id,
            target_domain="mobility",
            target_type="mobility.ride_request",
            target_id="ride-request-0001",
            continuity_reference="x" * 32,
            ttl=timedelta(seconds=30),
            idempotency_key="continuity-issue-0001",
            trace=_trace(),
            at=NOW,
        )
    with pytest.raises(ValueError, match="at least 32"):
        service.issue_continuity_reference(
            actor_account_id=account.account_id,
            acting_subject_id=account.subject_id,
            target_domain="mobility",
            target_type="mobility.ride_request",
            target_id="ride-request-0001",
            continuity_reference="short",
            ttl=timedelta(minutes=5),
            idempotency_key="continuity-issue-0002",
            trace=_trace(),
            at=NOW,
        )
    with pytest.raises(RequestAccessAuthorizationError, match="actor must match"):
        service.issue_continuity_reference(
            actor_account_id=account.account_id,
            acting_subject_id=uuid4(),
            target_domain="mobility",
            target_type="mobility.ride_request",
            target_id="ride-request-0001",
            continuity_reference="continuity-reference-explicit-0001",
            ttl=timedelta(minutes=5),
            idempotency_key="continuity-issue-0003",
            trace=_trace(),
            at=NOW,
        )
    unit.request_access.append_continuity.side_effect = lambda value: value
    issued = service.issue_continuity_reference(
        actor_account_id=account.account_id,
        acting_subject_id=account.subject_id,
        target_domain="mobility",
        target_type="mobility.ride_request",
        target_id="ride-request-0001",
        continuity_reference="continuity-reference-explicit-0001",
        ttl=timedelta(minutes=5),
        idempotency_key="continuity-issue-0004",
        trace=_trace(),
        at=NOW,
    )
    assert issued.expires_at == NOW + timedelta(minutes=5)


def test_interaction_provenance_rejects_actor_adapter_capability_and_replays() -> None:
    account, adapter = _account(), _adapter()
    capability = _capability(adapter)
    unit = _unit(account)
    unit.request_access.get_adapter.return_value = adapter
    unit.request_access.get_capability.return_value = capability
    unit.request_access.append_provenance.side_effect = lambda value: value
    service = _Service(unit)
    envelope = _envelope(account, adapter)

    with pytest.raises(ValueError, match="command identifier"):
        service.record_accepted_interaction(
            actor_account_id=account.account_id,
            envelope=envelope,
            interaction_idempotency_key="interaction-record-0001",
            trace=TraceContext.new(),
            at=NOW,
        )
    with pytest.raises(RequestAccessAuthorizationError, match="server actor"):
        service.record_accepted_interaction(
            actor_account_id=uuid4(),
            envelope=envelope,
            interaction_idempotency_key="interaction-record-0002",
            trace=_trace(),
            at=NOW,
        )
    mismatched = envelope.model_copy(update={"authenticated_subject_id": uuid4()})
    with pytest.raises(RequestAccessAuthorizationError, match="canonical Account"):
        service.record_accepted_interaction(
            actor_account_id=account.account_id,
            envelope=mismatched,
            interaction_idempotency_key="interaction-record-0003",
            trace=_trace(),
            at=NOW,
        )
    delegated = _envelope(account, adapter, acting_subject_id=uuid4())
    with pytest.raises(RequestAccessAuthorizationError, match="delegation integration"):
        service.record_accepted_interaction(
            actor_account_id=account.account_id,
            envelope=delegated,
            interaction_idempotency_key="interaction-record-0004",
            trace=_trace(),
            at=NOW,
        )

    unit.request_access.get_adapter.return_value = _adapter(active=False)
    with pytest.raises(RequestAccessAuthorizationError, match="source adapter"):
        service.record_accepted_interaction(
            actor_account_id=account.account_id,
            envelope=envelope,
            interaction_idempotency_key="interaction-record-0005",
            trace=_trace(),
            at=NOW,
        )
    unit.request_access.get_adapter.return_value = adapter
    unit.request_access.get_capability.return_value = capability.model_copy(
        update={"state": CapabilityState.DEGRADED}
    )
    with pytest.raises(
        RequestAccessAuthorizationError, match="not currently supported"
    ):
        service.record_accepted_interaction(
            actor_account_id=account.account_id,
            envelope=envelope,
            interaction_idempotency_key="interaction-record-0006",
            trace=_trace(),
            at=NOW,
        )

    unit.request_access.get_capability.return_value = capability
    record = service.record_accepted_interaction(
        actor_account_id=account.account_id,
        envelope=envelope,
        interaction_idempotency_key="interaction-record-0007",
        trace=_trace(),
        at=NOW,
    )
    assert record.purpose is ProvenancePurpose.INITIATION
    assert unit.events.append.call_args.args[0].event_type == (
        "access.interaction_provenance_recorded"
    )
    unit.idempotency.reserve.return_value = _reservation(
        account.account_id,
        completed=True,
        response=f"interaction_provenance/{record.provenance_id}",
    )
    unit.request_access.get_provenance.return_value = record
    assert (
        service.record_accepted_interaction(
            actor_account_id=account.account_id,
            envelope=envelope,
            interaction_idempotency_key="interaction-record-0007",
            trace=_trace(),
            at=NOW,
        )
        == record
    )
