from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from BACKEND.persistence.errors import IdempotencyConflictError
from BACKEND.persistence.tables import (
    account_role_assignments,
    audit_events,
    canonical_subjects,
    identity_accounts,
    permissions,
    persistence_domain_events,
    persistence_idempotency_records,
    persistence_outbox,
    request_access_continuity_references,
    request_access_interaction_provenance,
    role_permissions,
    roles,
)
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
    InteractionMethod,
    InteractionProvenanceEnvelope,
    ProvenancePurpose,
)

pytestmark = [pytest.mark.integration, pytest.mark.request_access]
NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def _principal(engine) -> tuple[UUID, UUID]:
    account_id, subject_id, role_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(canonical_subjects).values(
                subject_id=subject_id,
                subject_kind="human",
                created_at=NOW,
                version=1,
            )
        )
        connection.execute(
            insert(identity_accounts).values(
                account_id=account_id,
                subject_id=subject_id,
                state="active",
                created_at=NOW,
                updated_at=NOW,
                version=1,
                failed_attempt_count=0,
                credential_change_required=False,
            )
        )
        connection.execute(
            insert(roles).values(
                role_id=role_id,
                code=f"request_access_{account_id}",
                description="Request Access test principal",
                system_managed=False,
                created_at=NOW,
                version=1,
            )
        )
        for code in (
            "access.provenance.manage",
            "access.provenance.record",
            "access.provenance.support",
        ):
            permission_id = uuid4()
            connection.execute(
                insert(permissions).values(
                    permission_id=permission_id,
                    code=code,
                    description=code,
                    created_at=NOW,
                )
            )
            connection.execute(
                insert(role_permissions).values(
                    role_id=role_id,
                    permission_id=permission_id,
                    granted_at=NOW,
                )
            )
        connection.execute(
            insert(account_role_assignments).values(
                assignment_id=uuid4(),
                account_id=account_id,
                role_id=role_id,
                assigned_by_account_id=account_id,
                assigned_at=NOW,
                version=1,
            )
        )
    return account_id, subject_id


def _trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def _configured(
    engine,
) -> tuple[RequestAccessApplicationService, UUID, UUID, UUID]:
    service = RequestAccessApplicationService(engine)
    account_id, subject_id = _principal(engine)
    adapter = service.register_adapter(
        actor_account_id=account_id,
        command=RegisterSourceAdapter(
            adapter_code="ayo.mobile.reference",
            adapter_version=1,
            channel=AccessChannel.MOBILE_APP,
        ),
        idempotency_key=f"adapter-{uuid4()}",
        trace=_trace(),
        at=NOW,
    )
    service.declare_capability(
        actor_account_id=account_id,
        command=DeclareChannelCapability(
            target_domain="mobility",
            command_type="mobility.ride_request.create",
            adapter_id=adapter.adapter_id,
            state=CapabilityState.SUPPORTED,
            effective_from=NOW - timedelta(minutes=1),
        ),
        expected_version=None,
        idempotency_key=f"capability-{uuid4()}",
        trace=_trace(),
        at=NOW,
    )
    return service, account_id, subject_id, adapter.adapter_id


def _envelope(
    *,
    account_id: UUID,
    subject_id: UUID,
    adapter_id: UUID,
    target_id: str,
    purpose: ProvenancePurpose = ProvenancePurpose.INITIATION,
    continuity_reference: str | None = None,
) -> InteractionProvenanceEnvelope:
    return InteractionProvenanceEnvelope(
        purpose=purpose,
        target_domain="mobility",
        target_type="mobility.ride_request",
        target_id=target_id,
        target_version=1,
        command_type="mobility.ride_request.create",
        channel=AccessChannel.MOBILE_APP,
        interaction_method=InteractionMethod.SELF_SERVICE,
        adapter_id=adapter_id,
        adapter_version=1,
        authenticated_account_id=account_id,
        authenticated_subject_id=subject_id,
        acting_subject_id=subject_id,
        requester_subject_id=subject_id,
        passenger_subject_id=subject_id,
        continuity_reference=continuity_reference,
    )


def test_accepted_provenance_audit_event_outbox_and_restart_persistence(
    postgres_engine,
) -> None:
    service, account_id, subject_id, adapter_id = _configured(postgres_engine)
    target_id = str(uuid4())
    record = service.record_accepted_interaction(
        actor_account_id=account_id,
        envelope=_envelope(
            account_id=account_id,
            subject_id=subject_id,
            adapter_id=adapter_id,
            target_id=target_id,
        ),
        interaction_idempotency_key="interaction-initiation-0001",
        trace=_trace(),
        at=NOW,
    )

    restarted = RequestAccessApplicationService(postgres_engine)
    with restarted._uow() as unit:
        persisted = unit.request_access.get_provenance(record.provenance_id)
    with postgres_engine.connect() as connection:
        event = (
            connection.execute(
                select(persistence_domain_events).where(
                    persistence_domain_events.c.aggregate_id
                    == str(record.provenance_id)
                )
            )
            .mappings()
            .one()
        )
        outbox = (
            connection.execute(
                select(persistence_outbox).where(
                    persistence_outbox.c.event_id == event["event_id"]
                )
            )
            .mappings()
            .one()
        )
        audit = (
            connection.execute(
                select(audit_events).where(
                    audit_events.c.resource_id == str(record.provenance_id)
                )
            )
            .mappings()
            .one()
        )

    assert persisted == record
    assert event["event_type"] == "access.interaction_provenance_recorded"
    assert outbox["published_at"] is None
    assert audit["safe_metadata"]["category"] == "access_provenance"
    assert "language" not in event["payload"]


def test_interaction_retry_is_idempotent_and_conflicting_payload_is_rejected(
    postgres_engine,
) -> None:
    service, account_id, subject_id, adapter_id = _configured(postgres_engine)
    target_id = str(uuid4())
    trace = _trace()
    envelope = _envelope(
        account_id=account_id,
        subject_id=subject_id,
        adapter_id=adapter_id,
        target_id=target_id,
    )
    first = service.record_accepted_interaction(
        actor_account_id=account_id,
        envelope=envelope,
        interaction_idempotency_key="interaction-idempotency-0001",
        trace=trace,
        at=NOW,
    )
    second = service.record_accepted_interaction(
        actor_account_id=account_id,
        envelope=envelope,
        interaction_idempotency_key="interaction-idempotency-0001",
        trace=trace,
        at=NOW,
    )

    assert second.provenance_id == first.provenance_id
    with pytest.raises(IdempotencyConflictError):
        service.record_accepted_interaction(
            actor_account_id=account_id,
            envelope=envelope.model_copy(update={"target_version": 2}),
            interaction_idempotency_key="interaction-idempotency-0001",
            trace=_trace(),
            at=NOW,
        )


def test_explicit_cross_channel_continuity_is_hashed_and_target_bound(
    postgres_engine,
) -> None:
    service, account_id, subject_id, adapter_id = _configured(postgres_engine)
    target_id = str(uuid4())
    service.record_accepted_interaction(
        actor_account_id=account_id,
        envelope=_envelope(
            account_id=account_id,
            subject_id=subject_id,
            adapter_id=adapter_id,
            target_id=target_id,
        ),
        interaction_idempotency_key="interaction-initiation-0002",
        trace=_trace(),
        at=NOW,
    )
    issued = service.issue_continuity_reference(
        actor_account_id=account_id,
        acting_subject_id=subject_id,
        target_domain="mobility",
        target_type="mobility.ride_request",
        target_id=target_id,
        continuity_reference="continuity-reference-explicit-00000001",
        ttl=timedelta(hours=1),
        idempotency_key="continuity-issue-0001",
        trace=_trace(),
        at=NOW,
    )
    retried_issue = service.issue_continuity_reference(
        actor_account_id=account_id,
        acting_subject_id=subject_id,
        target_domain="mobility",
        target_type="mobility.ride_request",
        target_id=target_id,
        continuity_reference="continuity-reference-explicit-00000001",
        ttl=timedelta(hours=1),
        idempotency_key="continuity-issue-0001",
        trace=_trace(),
        at=NOW,
    )
    continued = service.record_accepted_interaction(
        actor_account_id=account_id,
        envelope=_envelope(
            account_id=account_id,
            subject_id=subject_id,
            adapter_id=adapter_id,
            target_id=target_id,
            purpose=ProvenancePurpose.CONTINUATION,
            continuity_reference=issued.reference,
        ),
        interaction_idempotency_key="interaction-continuation-0001",
        trace=_trace(),
        at=NOW + timedelta(minutes=1),
    )
    with postgres_engine.connect() as connection:
        stored = (
            connection.execute(
                select(request_access_continuity_references).where(
                    request_access_continuity_references.c.continuity_id
                    == issued.continuity_id
                )
            )
            .mappings()
            .one()
        )

    assert continued.continuity_id == issued.continuity_id
    assert retried_issue == issued
    assert issued.reference not in str(stored)
    with pytest.raises(RequestAccessAuthorizationError, match="target-mismatched"):
        service.record_accepted_interaction(
            actor_account_id=account_id,
            envelope=_envelope(
                account_id=account_id,
                subject_id=subject_id,
                adapter_id=adapter_id,
                target_id=str(uuid4()),
                purpose=ProvenancePurpose.CONTINUATION,
                continuity_reference=issued.reference,
            ),
            interaction_idempotency_key="interaction-continuation-0002",
            trace=_trace(),
            at=NOW + timedelta(minutes=1),
        )


def test_provenance_and_continuity_are_database_immutable(postgres_engine) -> None:
    service, account_id, subject_id, adapter_id = _configured(postgres_engine)
    target_id = str(uuid4())
    record = service.record_accepted_interaction(
        actor_account_id=account_id,
        envelope=_envelope(
            account_id=account_id,
            subject_id=subject_id,
            adapter_id=adapter_id,
            target_id=target_id,
        ),
        interaction_idempotency_key="interaction-immutable-0001",
        trace=_trace(),
        at=NOW,
    )
    issued = service.issue_continuity_reference(
        actor_account_id=account_id,
        acting_subject_id=subject_id,
        target_domain="mobility",
        target_type="mobility.ride_request",
        target_id=target_id,
        continuity_reference="continuity-reference-explicit-00000002",
        ttl=timedelta(hours=1),
        idempotency_key="continuity-issue-0002",
        trace=_trace(),
        at=NOW,
    )

    with pytest.raises(DBAPIError), postgres_engine.begin() as connection:
        connection.execute(
            update(request_access_interaction_provenance)
            .where(
                request_access_interaction_provenance.c.provenance_id
                == record.provenance_id
            )
            .values(target_version=2)
        )
    with pytest.raises(DBAPIError), postgres_engine.begin() as connection:
        connection.execute(
            delete(request_access_continuity_references).where(
                request_access_continuity_references.c.continuity_id
                == issued.continuity_id
            )
        )


def test_capability_optimistic_concurrency_and_failed_record_rollback(
    postgres_engine,
) -> None:
    service, account_id, subject_id, adapter_id = _configured(postgres_engine)
    existing = None
    with service._uow() as unit:
        existing = unit.request_access.get_capability(
            target_domain="mobility",
            command_type="mobility.ride_request.create",
            adapter_id=adapter_id,
        )
    assert existing is not None
    changed = service.declare_capability(
        actor_account_id=account_id,
        command=DeclareChannelCapability(
            target_domain=existing.target_domain,
            command_type=existing.command_type,
            adapter_id=adapter_id,
            state=CapabilityState.DEGRADED,
            effective_from=NOW,
        ),
        expected_version=1,
        idempotency_key="capability-change-0001",
        trace=_trace(),
        at=NOW,
    )
    assert changed.version == 2
    with pytest.raises(ValueError, match="Stale"):
        service.declare_capability(
            actor_account_id=account_id,
            command=DeclareChannelCapability(
                target_domain=existing.target_domain,
                command_type=existing.command_type,
                adapter_id=adapter_id,
                state=CapabilityState.SUPPORTED,
                effective_from=NOW,
            ),
            expected_version=1,
            idempotency_key="capability-change-0002",
            trace=_trace(),
            at=NOW,
        )

    with pytest.raises(
        RequestAccessAuthorizationError, match="not currently supported"
    ):
        service.record_accepted_interaction(
            actor_account_id=account_id,
            envelope=_envelope(
                account_id=account_id,
                subject_id=subject_id,
                adapter_id=adapter_id,
                target_id=str(uuid4()),
            ),
            interaction_idempotency_key="interaction-rollback-0001",
            trace=_trace(),
            at=NOW,
        )
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(request_access_interaction_provenance).where(
                    request_access_interaction_provenance.c.interaction_idempotency_key
                    == "interaction-rollback-0001"
                )
            ).first()
            is None
        )
        assert (
            connection.execute(
                select(persistence_idempotency_records).where(
                    persistence_idempotency_records.c.idempotency_key
                    == "interaction-rollback-0001"
                )
            ).first()
            is None
        )


def test_database_contains_no_unrestricted_metadata_columns(postgres_engine) -> None:
    with postgres_engine.connect() as connection:
        columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='ayo' AND "
                    "table_name='request_access_interaction_provenance'"
                )
            ).scalars()
        )

    assert {
        "transcript",
        "recording",
        "message_content",
        "phone_number",
        "email",
        "device_fingerprint",
        "advertising_id",
        "location_history",
        "metadata",
    }.isdisjoint(columns)
