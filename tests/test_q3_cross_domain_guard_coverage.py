from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.compatibility_models import AccountLifecycle, IdentityAccount
from BACKEND.identity.models import IdentityType
from BACKEND.payment.application import CallbackOutcome, PaymentOrchestrationService
from BACKEND.payment.engine import PaymentConflict
from BACKEND.payment.models import PaymentAttemptState, PaymentMethodFamily
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.trace import TraceContext
from BACKEND.request_access.application import (
    RequestAccessApplicationService,
    RequestAccessAuthorizationError,
)
from BACKEND.request_access.models import (
    AccessChannel,
    ContinuityReference,
    InteractionMethod,
    InteractionProvenanceEnvelope,
    ProvenancePurpose,
)
from BACKEND.ride_request.mobility_application import (
    PassengerMobilityRideRequestService,
    RideRequestAuthorizationError,
)
from BACKEND.service_area.application import (
    ServiceAreaApplicationService,
    ServiceAreaAuthorizationError,
)
from BACKEND.settlement.application import SettlementOrchestrationService
from BACKEND.settlement.engine import SettlementConflict
from BACKEND.settlement.models import (
    ReconciliationExceptionType,
    ReconciliationResult,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _account(*, active: bool = True) -> IdentityAccount:
    return IdentityAccount(
        subject_id=uuid4(),
        state=AccountLifecycle.ACTIVE if active else AccountLifecycle.SUSPENDED,
        created_at=NOW,
        updated_at=NOW,
    )


def _subject() -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )


def test_request_access_authority_continuity_and_evidence_are_fail_closed() -> None:
    account = _account()
    unit: Any = MagicMock()
    unit.accounts.get_account.return_value = account
    unit.accounts.has_permission.return_value = True
    assert (
        RequestAccessApplicationService._authorize(
            unit, account.account_id, "access.provenance.record", NOW
        )
        == account
    )
    unit.accounts.get_account.return_value = None
    with pytest.raises(RequestAccessAuthorizationError, match="Active canonical"):
        RequestAccessApplicationService._authorize(
            unit, account.account_id, "access.provenance.record", NOW
        )
    unit.accounts.get_account.return_value = account.model_copy(
        update={"state": AccountLifecycle.SUSPENDED}
    )
    with pytest.raises(RequestAccessAuthorizationError, match="Active canonical"):
        RequestAccessApplicationService._authorize(
            unit, account.account_id, "access.provenance.record", NOW
        )
    unit.accounts.get_account.return_value = account
    unit.accounts.has_permission.return_value = False
    with pytest.raises(RequestAccessAuthorizationError, match="permission required"):
        RequestAccessApplicationService._authorize(
            unit, account.account_id, "access.provenance.record", NOW
        )

    raw = "explicit-continuity-reference-value-0001"
    reference = ContinuityReference(
        continuity_id=uuid4(),
        reference_hash=RequestAccessApplicationService._hash_reference(raw),
        authenticated_account_id=account.account_id,
        acting_subject_id=account.subject_id,
        target_domain="mobility",
        target_type="ride_request",
        target_id="ride-request-0001",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    envelope = InteractionProvenanceEnvelope(
        purpose=ProvenancePurpose.CONTINUATION,
        target_domain=reference.target_domain,
        target_type=reference.target_type,
        target_id=reference.target_id,
        target_version=1,
        command_type="ride_request.continue",
        channel=AccessChannel.MOBILE_APP,
        interaction_method=InteractionMethod.SELF_SERVICE,
        adapter_id=uuid4(),
        adapter_version=1,
        authenticated_account_id=account.account_id,
        authenticated_subject_id=account.subject_id,
        acting_subject_id=account.subject_id,
        continuity_reference=raw,
    )
    unit.request_access.get_continuity_by_hash.return_value = reference
    assert (
        RequestAccessApplicationService._validate_continuity(
            unit, envelope=envelope, at=NOW
        )
        == reference.continuity_id
    )
    initiation = envelope.model_copy(
        update={
            "purpose": ProvenancePurpose.INITIATION,
            "continuity_reference": None,
        }
    )
    assert (
        RequestAccessApplicationService._validate_continuity(
            unit, envelope=initiation, at=NOW
        )
        is None
    )
    unit.request_access.get_continuity_by_hash.return_value = None
    with pytest.raises(RequestAccessAuthorizationError, match="invalid, expired"):
        RequestAccessApplicationService._validate_continuity(
            unit, envelope=envelope, at=NOW
        )

    trace = TraceContext.new().child(command_id=uuid4())
    unit.events.append = MagicMock()
    unit.audit.append = MagicMock()
    RequestAccessApplicationService._record_evidence(
        unit,
        trace=trace,
        actor_account_id=account.account_id,
        resource_id=uuid4(),
        aggregate_type="access.provenance",
        event_type="access.provenance.recorded",
        payload={"schema_version": 1},
        idempotency_key="provenance-record-0001",
        at=NOW,
    )
    assert unit.events.append.call_args.args[0].correlation_id == trace.correlation_id
    assert unit.audit.append.call_args.args[0].safe_metadata["category"] == (
        "access_provenance"
    )


def test_request_access_service_area_and_mobility_require_command_context() -> None:
    unit: Any = MagicMock()
    no_command = TraceContext.new()
    with pytest.raises(ValueError, match="command identifier"):
        RequestAccessApplicationService._reserve(
            unit,
            uuid4(),
            "record",
            "material",
            "idempotency-key-0001",
            no_command,
            NOW,
        )
    with pytest.raises(ValueError, match="command identifier"):
        ServiceAreaApplicationService._reserve_raw(
            unit,
            uuid4(),
            "create",
            "material",
            "idempotency-key-0002",
            no_command,
            NOW,
        )
    with pytest.raises(ValueError, match="command identifier"):
        PassengerMobilityRideRequestService._command_id(no_command)
    command = no_command.child(command_id=uuid4())
    unit.idempotency.reserve.side_effect = lambda value: value
    assert (
        RequestAccessApplicationService._reserve(
            unit,
            uuid4(),
            "record",
            "material",
            "idempotency-key-0003",
            command,
            NOW,
        ).command_id
        == command.command_id
    )
    assert (
        ServiceAreaApplicationService._reserve_raw(
            unit,
            uuid4(),
            "create",
            "material",
            "idempotency-key-0004",
            command,
            NOW,
        ).command_id
        == command.command_id
    )


def test_service_area_and_mobility_authority_reuse_canonical_sources() -> None:
    account = _account()
    unit: Any = MagicMock()
    unit.accounts.get_account.return_value = account
    unit.accounts.has_permission.return_value = True
    ServiceAreaApplicationService._authorize(
        unit, account.account_id, "service_area.manage", NOW
    )
    assert (
        PassengerMobilityRideRequestService._active_account(unit, account.account_id)
        == account
    )
    unit.accounts.get_account.return_value = None
    with pytest.raises(ServiceAreaAuthorizationError, match="Active canonical"):
        ServiceAreaApplicationService._authorize(
            unit, account.account_id, "service_area.manage", NOW
        )
    with pytest.raises(RideRequestAuthorizationError, match="Active canonical"):
        PassengerMobilityRideRequestService._active_account(unit, account.account_id)

    requester, passenger = uuid4(), uuid4()
    PassengerMobilityRideRequestService._require_passenger_authority(
        unit, requester, requester
    )
    unit.profiles.active_relationship_between.return_value = object()
    PassengerMobilityRideRequestService._require_passenger_authority(
        unit, requester, passenger
    )
    unit.profiles.active_relationship_between.return_value = None
    with pytest.raises(RideRequestAuthorizationError, match="trusted household"):
        PassengerMobilityRideRequestService._require_passenger_authority(
            unit, requester, passenger
        )
    unit.accounts.has_permission.return_value = False
    assert (
        PassengerMobilityRideRequestService._administrative_override(
            unit, account.account_id, False, NOW
        )
        is False
    )
    assert (
        PassengerMobilityRideRequestService._administrative_override(
            unit, account.account_id, True, NOW
        )
        is False
    )


def test_payment_guards_callback_mapping_and_participant_authority() -> None:
    composition: Any = MagicMock()
    composition.unit_of_work.return_value.__enter__.return_value = MagicMock()
    service = PaymentOrchestrationService(
        cast(PostgresRepositoryComposition, composition)
    )
    subject = _subject()
    service._authorize_participants(
        subject,
        payer_identity_id=subject.identity_id,
        passenger_identity_id=subject.identity_id,
        booker_identity_id=subject.identity_id,
        third_party_booking_authorized=False,
        at=NOW,
    )
    with pytest.raises(PaymentConflict, match="payer_authority_required"):
        service._authorize_participants(
            subject,
            payer_identity_id=uuid4(),
            passenger_identity_id=subject.identity_id,
            booker_identity_id=subject.identity_id,
            third_party_booking_authorized=False,
            at=NOW,
        )
    with pytest.raises(PaymentConflict, match="third_party_booking_authority"):
        service._authorize_participants(
            subject,
            payer_identity_id=subject.identity_id,
            passenger_identity_id=uuid4(),
            booker_identity_id=subject.identity_id,
            third_party_booking_authorized=False,
            at=NOW,
        )
    with pytest.raises(PaymentConflict, match="idempotency_key_invalid"):
        service._validate_idempotency_key("short")

    for outcome, expected in {
        "authorized": PaymentAttemptState.AUTHORIZED,
        "capture_pending": PaymentAttemptState.CAPTURE_PENDING,
        "captured": PaymentAttemptState.CAPTURED,
        "failed": PaymentAttemptState.FAILED,
        "cancelled": PaymentAttemptState.CANCELLED,
        "expired": PaymentAttemptState.EXPIRED,
        "unknown": PaymentAttemptState.OUTCOME_UNKNOWN,
    }.items():
        callback = CallbackOutcome(
            outcome=outcome, provider_event_id="provider-event", payload={}
        )
        assert (
            service._callback_target_state(PaymentMethodFamily.CARD, callback)
            is expected
        )
    assert (
        service._callback_target_state(
            PaymentMethodFamily.CASH,
            CallbackOutcome(
                outcome="captured", provider_event_id="provider-event", payload={}
            ),
        )
        is PaymentAttemptState.OUTCOME_UNKNOWN
    )
    invalid = CallbackOutcome(
        outcome="unsupported", provider_event_id="provider-event", payload={}
    )
    with pytest.raises(PaymentConflict, match="outcome_invalid"):
        service._callback_target_state(PaymentMethodFamily.CARD, invalid)
    for state in PaymentAttemptState:
        assert service._callback_reason(state).startswith("payment.callback.")


def test_settlement_guards_and_exception_taxonomy_are_closed() -> None:
    service = SettlementOrchestrationService(
        cast(PostgresRepositoryComposition, MagicMock())
    )
    with pytest.raises(SettlementConflict, match="idempotency_key_invalid"):
        service._validate_idempotency_key("short")
    expected = {
        ReconciliationResult.MISMATCH: ReconciliationExceptionType.AMOUNT_MISMATCH,
        ReconciliationResult.MISSING: ReconciliationExceptionType.MISSING_CALLBACK,
        ReconciliationResult.DUPLICATE: ReconciliationExceptionType.DUPLICATE_PAYMENT,
        ReconciliationResult.MANUAL_REVIEW_REQUIRED: (
            ReconciliationExceptionType.MANUAL_INVESTIGATION
        ),
        ReconciliationResult.MATCHED: ReconciliationExceptionType.UNKNOWN_OUTCOME,
        ReconciliationResult.PARTIALLY_MATCHED: (
            ReconciliationExceptionType.REFUND_MISMATCH
        ),
    }
    assert {
        result: service._exception_from_result(result)
        for result in ReconciliationResult
    } == expected


@pytest.mark.parametrize(
    "function",
    [
        RequestAccessApplicationService._at,
        ServiceAreaApplicationService._at,
        PassengerMobilityRideRequestService._at,
    ],
)
def test_cross_domain_timestamps_reject_naive_values(function: Any) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        function(datetime(2026, 7, 24, 12))
    assert function(NOW).tzinfo is UTC
