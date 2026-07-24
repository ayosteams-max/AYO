from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.field_operations.application import (
    FieldOperationsApplication,
    FieldOperationsConflict,
)
from BACKEND.field_operations.models import (
    AssistanceCase,
    FieldPartner,
    PartnerAssignment,
    PartnerStatus,
    VerificationStatus,
)
from BACKEND.identity.access_models import AccountSession, PasswordCredential
from BACKEND.identity.account_access_service import AccountAccessService
from BACKEND.identity.compatibility_models import AccountLifecycle, IdentityAccount
from BACKEND.identity.models import IdentityType
from BACKEND.identity.runtime import (
    AuthenticationDenied,
    AuthenticationRateLimited,
    AuthenticationRuntime,
)
from BACKEND.payment.application import CallbackOutcome, PaymentOrchestrationService
from BACKEND.payment.engine import PaymentConflict
from BACKEND.payment.models import (
    PaymentAttempt,
    PaymentAttemptState,
    PaymentIntent,
    PaymentIntentState,
    PaymentMethodFamily,
    PaymentTraceability,
)
from BACKEND.persistence.kernel_models import IdempotencyRecord
from BACKEND.persistence.payment_repository import PostgresPaymentRepository
from BACKEND.persistence.settlement_repository import PostgresSettlementRepository
from BACKEND.persistence.trace import TraceContext
from BACKEND.settlement.application import SettlementOrchestrationService
from BACKEND.settlement.engine import SettlementConflict
from BACKEND.settlement.models import (
    SettlementApproval,
    SettlementApprovalDecision,
    SettlementBatch,
    SettlementBatchState,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class _Passwords:
    scheme = "test-password"

    def hash(self, value: str) -> str:
        return f"hashed-{value}".ljust(32, "x")

    def verify(self, verifier: str, value: str) -> bool:
        return verifier == self.hash(value)

    def needs_upgrade(self, verifier: str) -> bool:
        return verifier.startswith("legacy-")


class _AccountService(AccountAccessService):
    test_unit: Any

    def _uow(self) -> Any:
        return nullcontext(self.test_unit)


def _reservation(
    *, completed: bool = False, response: str | None = None
) -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="test.operation",
        actor_reference=str(uuid4()),
        idempotency_key="idempotency-key-0001",
        request_hash="a" * 64,
        command_id=uuid4(),
        correlation_id=uuid4(),
        request_id=uuid4(),
        response_reference=response,
        created_at=NOW,
        completed_at=NOW if completed else None,
    )


def _account(state: AccountLifecycle = AccountLifecycle.ACTIVE) -> IdentityAccount:
    return IdentityAccount(
        subject_id=uuid4(), state=state, created_at=NOW, updated_at=NOW
    )


def _account_service(unit: Any) -> _AccountService:
    service = object.__new__(_AccountService)
    service.test_unit = unit
    service._passwords = cast(Any, _Passwords())
    service._dummy_verifier = "dummy-verifier".ljust(32, "x")
    service._security_pepper = b"x" * 32
    service._failed_attempt_limit = 3
    service._failed_attempt_window = timedelta(minutes=15)
    service._origin_attempt_limit = 20
    service._origin_attempt_window = timedelta(minutes=5)
    service._absolute_lifetime = timedelta(days=7)
    service._inactivity_timeout = timedelta(hours=12)
    return service


def _trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def test_account_password_set_is_retry_safe_and_closed_accounts_fail() -> None:
    unit: Any = MagicMock()
    account = _account()
    unit.idempotency.reserve.return_value = _reservation()
    unit.access.get_account.return_value = account
    unit.access.active_credential.return_value = None
    service = _account_service(unit)

    credential = service.set_password(
        account_id=account.account_id,
        password="correct horse battery staple",
        idempotency_key="password-set-0001",
        trace=_trace(),
        at=NOW,
    )
    assert credential.account_id == account.account_id
    assert credential.credential_version == 1
    unit.access.replace_credential.assert_called_once()
    unit.events.append.assert_called_once()
    unit.audit.append.assert_called_once()
    unit.idempotency.complete.assert_called_once()

    unit.reset_mock()
    existing = credential.model_copy(update={"credential_version": 4})
    unit.idempotency.reserve.return_value = _reservation(
        completed=True, response=f"credential/{existing.credential_id}"
    )
    unit.access.active_credential.return_value = existing
    assert (
        service.set_password(
            account_id=account.account_id,
            password="correct horse battery staple",
            idempotency_key="password-set-0001",
            trace=_trace(),
            at=NOW,
        )
        == existing
    )
    unit.access.replace_credential.assert_not_called()

    unit.idempotency.reserve.return_value = _reservation()
    unit.access.active_credential.return_value = None
    unit.access.get_account.return_value = _account(AccountLifecycle.CLOSED)
    with pytest.raises(ValueError, match="Account is unavailable"):
        service.set_password(
            account_id=account.account_id,
            password="correct horse battery staple",
            idempotency_key="password-set-0002",
            trace=_trace(),
            at=NOW,
        )


def test_account_authentication_throttle_denial_success_and_replay() -> None:
    unit: Any = MagicMock()
    account = _account()
    credential = PasswordCredential(
        account_id=account.account_id,
        credential_version=1,
        scheme="test-password",
        verifier=_Passwords().hash("valid password phrase"),
        created_at=NOW,
    )
    unit.idempotency.reserve.return_value = _reservation()
    unit.access.consume_origin_attempt.return_value = False
    service = _account_service(unit)

    throttled = service.authenticate(
        account_id=account.account_id,
        password="valid password phrase",
        client_reference="client",
        client_origin="coarse-origin",
        idempotency_key="authenticate-0001",
        trace=_trace(),
        at=NOW,
    )
    assert not throttled.authenticated
    unit.access.get_account.assert_not_called()

    unit.reset_mock()
    unit.idempotency.reserve.return_value = _reservation()
    unit.access.get_account.return_value = account
    unit.access.active_credential.return_value = credential
    unit.access.record_failed_attempt.return_value = account
    denied = service.authenticate(
        account_id=account.account_id,
        password="wrong password phrase",
        client_reference=None,
        idempotency_key="authenticate-0002",
        trace=_trace(),
        at=NOW,
    )
    assert not denied.authenticated
    unit.access.record_failed_attempt.assert_called_once()

    unit.reset_mock()
    unit.idempotency.reserve.return_value = _reservation()
    unit.access.get_account.return_value = account
    unit.access.active_credential.return_value = credential
    unit.access.reset_failed_attempts.return_value = account
    result = service.authenticate(
        account_id=account.account_id,
        password="valid password phrase",
        client_reference="client",
        idempotency_key="authenticate-0003",
        trace=_trace(),
        at=NOW,
    )
    assert result.authenticated and result.session_id is not None
    unit.access.create_session.assert_called_once()

    unit.reset_mock()
    unit.idempotency.reserve.return_value = _reservation(
        completed=True, response=f"session/{result.session_id}"
    )
    replay = service.authenticate(
        account_id=account.account_id,
        password="ignored password phrase",
        client_reference=None,
        idempotency_key="authenticate-0003",
        trace=_trace(),
        at=NOW,
    )
    assert replay == result
    unit.access.get_account.assert_not_called()


def test_account_session_validation_fails_closed_and_touches_valid_session() -> None:
    unit: Any = MagicMock()
    account = _account()
    session = AccountSession(
        account_id=account.account_id,
        created_at=NOW,
        last_used_at=NOW,
        absolute_expires_at=NOW + timedelta(days=1),
        inactivity_seconds=3600,
    )
    service = _account_service(unit)

    unit.access.get_session.return_value = None
    assert service.validate_session(session.session_id, at=NOW) is None
    unit.access.get_session.return_value = session
    unit.access.get_account.return_value = _account(AccountLifecycle.SUSPENDED)
    assert service.validate_session(session.session_id, at=NOW) is None
    unit.access.get_account.return_value = account
    unit.access.touch_session.return_value = session
    assert service.validate_session(session.session_id, at=NOW) == session


def _subject(
    identity_type: IdentityType = IdentityType.SERVICE,
) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=identity_type,
        actor_type=(
            ActorType.SERVICE
            if identity_type is IdentityType.SERVICE
            else ActorType.RIDER
        ),
    )


def _composition(unit: Any) -> Any:
    composition: Any = MagicMock()
    composition.unit_of_work.side_effect = lambda: nullcontext(unit)
    return composition


def _intent(*, state: PaymentIntentState = PaymentIntentState.CREATED) -> PaymentIntent:
    identity = uuid4()
    return PaymentIntent(
        ride_id=uuid4(),
        rider_identity_id=identity,
        passenger_identity_id=identity,
        booker_identity_id=identity,
        payer_identity_id=identity,
        amount_minor=1000,
        currency="ETB",
        payment_method_family=PaymentMethodFamily.CARD,
        state=state,
        traceability=PaymentTraceability(
            ride_request_id=uuid4(),
            dispatch_handoff_id=uuid4(),
            assignment_id=uuid4(),
            active_ride_id=uuid4(),
            fare_estimate_id=uuid4(),
            fare_calculation_id=uuid4(),
            ledger_journal_id=uuid4(),
        ),
        created_at=NOW,
    )


def test_payment_attempt_creation_replay_missing_expired_and_inactive() -> None:
    unit: Any = MagicMock()
    unit.authorization.has_permission.return_value = True
    intent = _intent()
    rider = _subject(IdentityType.RIDER).model_copy(
        update={"identity_id": intent.rider_identity_id}
    )
    unit.payments.reserve_idempotency.return_value = uuid4()
    unit.payments.get_attempt.return_value = None
    unit.payments.get_intent.return_value = None
    service = PaymentOrchestrationService(_composition(unit))
    with pytest.raises(PaymentConflict, match="payment_intent_not_found"):
        service.create_payment_attempt(
            rider,
            payment_intent_id=intent.payment_intent_id,
            provider_code="provider",
            provider_reference="reference",
            idempotency_key="attempt-create-0001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )

    unit.payments.get_intent.return_value = intent.model_copy(
        update={"expires_at": NOW}
    )
    with pytest.raises(PaymentConflict, match="payment_intent_expired"):
        service.create_payment_attempt(
            rider,
            payment_intent_id=intent.payment_intent_id,
            provider_code="provider",
            provider_reference="reference",
            idempotency_key="attempt-create-0002",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )
    unit.payments.get_intent.return_value = intent.model_copy(
        update={"state": PaymentIntentState.CANCELLED}
    )
    with pytest.raises(PaymentConflict, match="payment_intent_not_active"):
        service.create_payment_attempt(
            rider,
            payment_intent_id=intent.payment_intent_id,
            provider_code="provider",
            provider_reference="reference",
            idempotency_key="attempt-create-0003",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )

    existing = PaymentAttempt(
        payment_intent_id=intent.payment_intent_id,
        provider_code="provider",
        provider_reference="reference",
        state=PaymentAttemptState.CREATED,
        amount_minor=1000,
        currency="ETB",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )
    unit.payments.get_attempt.return_value = existing
    assert (
        service.create_payment_attempt(
            rider,
            payment_intent_id=intent.payment_intent_id,
            provider_code="provider",
            provider_reference="reference",
            idempotency_key="attempt-create-0004",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )
        == existing
    )


def test_settlement_batch_creation_is_service_only_and_idempotent() -> None:
    unit: Any = MagicMock()
    unit.authorization.has_permission.return_value = True
    canonical = uuid4()
    unit.settlements.reserve_idempotency.return_value = canonical
    unit.settlements.get_batch.return_value = None
    service = SettlementOrchestrationService(_composition(unit))

    with pytest.raises(SettlementConflict, match="service_identity_required"):
        service.create_batch(
            _subject(IdentityType.RIDER),
            idempotency_key="settlement-batch-0001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )

    service_subject = _subject()
    created = SettlementBatch(
        settlement_batch_id=canonical,
        state=SettlementBatchState.CREATED,
        created_by_identity_id=service_subject.identity_id,
        created_at=NOW,
        last_transition_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )
    unit.settlements.create_batch.return_value = created
    assert (
        service.create_batch(
            service_subject,
            idempotency_key="settlement-batch-0002",
            correlation_id=created.correlation_id,
            causation_id=created.causation_id,
            at=NOW,
        )
        == created
    )

    unit.settlements.get_batch.return_value = created
    unit.settlements.create_batch.reset_mock()
    assert (
        service.create_batch(
            service_subject,
            idempotency_key="settlement-batch-0002",
            correlation_id=created.correlation_id,
            causation_id=created.causation_id,
            at=NOW,
        )
        == created
    )
    unit.settlements.create_batch.assert_not_called()


def test_payment_submission_callback_and_cancellation_boundaries() -> None:
    unit: Any = MagicMock()
    unit.authorization.has_permission.return_value = True
    intent = _intent()
    rider = _subject(IdentityType.RIDER).model_copy(
        update={"identity_id": intent.rider_identity_id}
    )
    attempt = PaymentAttempt(
        payment_intent_id=intent.payment_intent_id,
        provider_code="provider",
        provider_reference="reference",
        state=PaymentAttemptState.CREATED,
        amount_minor=intent.amount_minor,
        currency=intent.currency,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )
    unit.payments.get_attempt.return_value = attempt
    unit.payments.get_intent.return_value = intent
    unit.payments.transition_attempt.return_value = attempt.model_copy(
        update={"state": PaymentAttemptState.AUTHORIZATION_PENDING}
    )
    service = PaymentOrchestrationService(_composition(unit))

    submitted = service.submit_provider_neutral_attempt(
        rider,
        payment_attempt_id=attempt.payment_attempt_id,
        idempotency_key="attempt-submit-0001",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert submitted.state is PaymentAttemptState.AUTHORIZATION_PENDING
    assert (
        unit.payments.transition_attempt.call_args.kwargs["reason_code"]
        == "payment.authorization.submitted"
    )

    unit.payments.get_attempt.return_value = None
    with pytest.raises(PaymentConflict, match="payment_attempt_not_found"):
        service.submit_provider_neutral_attempt(
            rider,
            payment_attempt_id=attempt.payment_attempt_id,
            idempotency_key="attempt-submit-0002",
            correlation_id=uuid4(),
            at=NOW,
        )

    unit.payments.get_attempt.return_value = attempt
    unit.payments.get_intent.return_value = intent
    unit.payments.list_attempts_for_intent.return_value = (
        attempt.model_copy(update={"state": PaymentAttemptState.CAPTURED}),
    )
    with pytest.raises(PaymentConflict, match="payment_intent_cancel_forbidden"):
        service.cancel_intent(
            rider,
            payment_intent_id=intent.payment_intent_id,
            reason_code="customer_cancelled",
            correlation_id=uuid4(),
            at=NOW,
        )

    service_subject = _subject()
    with pytest.raises(PaymentConflict, match="payment_callback_provider_mismatch"):
        service.ingest_authenticated_callback_envelope(
            service_subject,
            payment_attempt_id=attempt.payment_attempt_id,
            provider_code="wrong-provider",
            signature_fingerprint="fingerprint",
            callback=CallbackOutcome(
                outcome="failed", provider_event_id="event-123", payload={}
            ),
            idempotency_key="callback-ingest-0001",
            correlation_id=uuid4(),
            at=NOW,
        )


def test_settlement_balancing_rejects_missing_state_items_and_exceptions() -> None:
    unit: Any = MagicMock()
    unit.authorization.has_permission.return_value = True
    subject = _subject()
    batch = SettlementBatch(
        state=SettlementBatchState.CREATED,
        created_by_identity_id=subject.identity_id,
        created_at=NOW,
        last_transition_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )
    unit.settlements.get_batch.return_value = None
    service = SettlementOrchestrationService(_composition(unit))
    correlation_id = uuid4()

    def mark_balanced() -> SettlementBatch:
        return service.mark_balanced(
            subject,
            settlement_batch_id=batch.settlement_batch_id,
            reason_code="reconciled",
            idempotency_key="settlement-balance-0001",
            correlation_id=correlation_id,
            at=NOW,
        )

    with pytest.raises(SettlementConflict, match="settlement_batch_not_found"):
        mark_balanced()

    unit.settlements.get_batch.return_value = batch
    with pytest.raises(SettlementConflict, match="settlement_batch_not_reconciling"):
        mark_balanced()

    reconciling = batch.model_copy(update={"state": SettlementBatchState.RECONCILING})
    unit.settlements.get_batch.return_value = reconciling
    unit.settlements.list_exceptions.return_value = (MagicMock(),)
    with pytest.raises(SettlementConflict, match="settlement_batch_has_exceptions"):
        mark_balanced()

    unit.settlements.list_exceptions.return_value = ()
    unit.settlements.list_items.return_value = ()
    with pytest.raises(SettlementConflict, match="settlement_batch_no_items"):
        mark_balanced()

    balanced = reconciling.model_copy(update={"state": SettlementBatchState.BALANCED})
    unit.settlements.list_items.return_value = (MagicMock(),)
    unit.settlements.transition_batch.return_value = balanced
    assert mark_balanced() == balanced


def test_identity_runtime_token_and_rate_limit_helpers_fail_closed() -> None:
    family_id = uuid4()
    token = AuthenticationRuntime._new_refresh_token(family_id)
    assert AuthenticationRuntime._family_id(token) == family_id
    assert AuthenticationRuntime._token_hash(token) == (
        AuthenticationRuntime._token_hash(token)
    )
    with pytest.raises(AuthenticationDenied, match="refresh_denied"):
        AuthenticationRuntime._family_id("invalid")

    unit: Any = MagicMock()
    unit.rate_limits.consume.return_value.allowed = True
    policy: Any = MagicMock()
    AuthenticationRuntime._enforce_rate_limit(unit, b"key", policy)
    unit.commit.assert_not_called()
    unit.rate_limits.consume.return_value.allowed = False
    unit.rate_limits.consume.return_value.retry_after_seconds = 17
    with pytest.raises(AuthenticationRateLimited) as error:
        AuthenticationRuntime._enforce_rate_limit(unit, b"key", policy)
    assert error.value.retry_after_seconds == 17
    unit.commit.assert_called_once()


def test_field_operations_qr_permissions_and_assignment_scope_fail_closed() -> None:
    unit: Any = MagicMock()
    composition = _composition(unit)
    service = FieldOperationsApplication(composition)
    partner = FieldPartner(
        public_partner_id="AYO-FP-ABCDEF12",
        identity_id=uuid4(),
        photo_reference="photo-reference-0001",
        qr_reference_hash=service._hash("qr-reference"),
        verification_status=VerificationStatus.VERIFIED,
        status=PartnerStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    unit.field_operations.partner_by_qr_hash.return_value = partner
    assert service.verify_public_qr(qr_reference="qr-reference") == {
        "partner_id": partner.public_partner_id,
        "verified": True,
        "active": True,
    }
    unit.field_operations.partner_by_qr_hash.return_value = None
    with pytest.raises(FieldOperationsConflict, match="field_partner_not_found"):
        service.verify_public_qr(qr_reference="unknown")

    subject = _subject(IdentityType.RIDER).model_copy(
        update={"identity_id": partner.identity_id}
    )
    case = AssistanceCase(
        partner_id=partner.partner_id,
        territory_id=uuid4(),
        subject_type="merchant",
        subject_id=uuid4(),
        capability_code="merchant.onboard",
        created_at=NOW,
        updated_at=NOW,
    )
    unit.field_operations.partner_for_identity.return_value = None
    with pytest.raises(
        FieldOperationsConflict, match="field_case_representative_required"
    ):
        service._assert_case_representative(unit, subject, case, NOW)
    unit.field_operations.partner_for_identity.return_value = partner
    unit.field_operations.active_assignments.return_value = ()
    with pytest.raises(FieldOperationsConflict, match="field_assignment_not_active"):
        service._assert_case_representative(unit, subject, case, NOW)
    unit.field_operations.active_assignments.return_value = (
        PartnerAssignment(
            partner_id=partner.partner_id,
            role_id=uuid4(),
            territory_id=case.territory_id,
            starts_at=NOW,
        ),
    )
    service._assert_case_representative(unit, subject, case, NOW)

    unit.authorization.has_permission.return_value = False
    with pytest.raises(FieldOperationsConflict, match="access_denied"):
        service._permission(unit, subject, "field.case.read", NOW)


def test_payment_status_history_and_transition_reads_do_not_leak() -> None:
    unit: Any = MagicMock()
    intent = _intent()
    rider = _subject(IdentityType.RIDER).model_copy(
        update={"identity_id": intent.rider_identity_id}
    )
    unit.authorization.has_permission.return_value = True
    service = PaymentOrchestrationService(_composition(unit))

    unit.payments.get_intent.return_value = None
    with pytest.raises(PaymentConflict, match="payment_status_not_found"):
        service.payment_status(
            rider, payment_intent_id=intent.payment_intent_id, at=NOW
        )
    unit.payments.get_intent.return_value = intent
    unit.payments.list_attempts_for_intent.return_value = ()
    status = service.payment_status(
        rider, payment_intent_id=intent.payment_intent_id, at=NOW
    )
    assert status.payment_intent == intent and status.payment_attempts == ()

    unit.payments.payment_history_by_ride.return_value = ((), {})
    with pytest.raises(PaymentConflict, match="payment_history_not_found"):
        service.payment_history_by_ride(rider, ride_id=intent.ride_id, at=NOW)
    unit.payments.payment_history_by_ride.return_value = ((intent,), {})
    history = service.payment_history_by_ride(rider, ride_id=intent.ride_id, at=NOW)
    assert history.ride_id == intent.ride_id
    assert history.statuses[0].payment_attempts == ()

    unit.payments.transition_intent.return_value = intent.model_copy(
        update={"state": PaymentIntentState.EXPIRED}
    )
    assert (
        service.expire_intent(
            rider,
            payment_intent_id=intent.payment_intent_id,
            reason_code="payment.expired",
            correlation_id=uuid4(),
            at=NOW,
        ).state
        is PaymentIntentState.EXPIRED
    )


def test_settlement_human_approval_enforces_state_identity_and_maker_checker() -> None:
    unit: Any = MagicMock()
    unit.authorization.has_permission.return_value = True
    creator = _subject()
    batch = SettlementBatch(
        state=SettlementBatchState.BALANCED,
        created_by_identity_id=creator.identity_id,
        created_at=NOW,
        last_transition_at=NOW,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )
    unit.settlements.get_batch.return_value = batch
    service = SettlementOrchestrationService(_composition(unit))
    correlation_id = uuid4()

    def approve(subject: AuthorizationSubject) -> SettlementApproval:
        return service.approve_settlement_readiness(
            subject,
            settlement_batch_id=batch.settlement_batch_id,
            reason_code="finance_reviewed",
            idempotency_key="finance-approval-0001",
            correlation_id=correlation_id,
            at=NOW,
        )

    with pytest.raises(SettlementConflict, match="human_approval_required"):
        approve(creator)

    staff = AuthorizationSubject(
        identity_id=batch.created_by_identity_id,
        identity_type=IdentityType.STAFF,
        actor_type=ActorType.STAFF,
    )
    with pytest.raises(SettlementConflict, match="maker_checker_required"):
        approve(staff)

    reviewer = staff.model_copy(update={"identity_id": uuid4()})
    approval = SettlementApproval(
        settlement_batch_id=batch.settlement_batch_id,
        decision=SettlementApprovalDecision.APPROVED,
        reason_code="finance_reviewed",
        prepared_by_identity_id=batch.created_by_identity_id,
        decided_by_identity_id=reviewer.identity_id,
        decided_by_actor_type=reviewer.actor_type.value,
        decided_at=NOW,
        correlation_id=correlation_id,
        causation_id=batch.settlement_batch_id,
    )
    unit.settlements.append_approval.return_value = approval
    assert approve(reviewer) == approval


def test_financial_persistence_payload_hash_is_canonical_and_sensitive() -> None:
    first = {"provider": "telebirr", "amount": 1000}
    reordered = {"amount": 1000, "provider": "telebirr"}
    changed = {"provider": "telebirr", "amount": 1001}
    assert PostgresPaymentRepository.payload_hash(
        first
    ) == PostgresPaymentRepository.payload_hash(reordered)
    assert PostgresSettlementRepository.payload_hash(
        first
    ) == PostgresSettlementRepository.payload_hash(reordered)
    assert PostgresPaymentRepository.payload_hash(
        first
    ) != PostgresPaymentRepository.payload_hash(changed)
