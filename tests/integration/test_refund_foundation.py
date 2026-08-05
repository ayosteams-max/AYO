from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.identity.models import IdentityType
from BACKEND.payment.application import CallbackOutcome, PaymentOrchestrationService
from BACKEND.payment.models import PaymentAttemptState, PaymentMethodFamily
from BACKEND.persistence.tables import refund_events, refund_outbox
from BACKEND.refund.application import RefundOrchestrationService
from BACKEND.refund.engine import RefundConflict
from BACKEND.refund.models import RefundRequestState, RefundType
from tests.integration.test_payment_foundation import (
    NOW,
    create_identity,
    existing_identity_ref,
    grant_permissions,
    payable_context,
    subject,
)

pytestmark = [pytest.mark.integration]


def _captured_attempt(
    postgres_composition,
    *,
    callback_identity_id: UUID,
):
    context = payable_context(postgres_composition)
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    grant_permissions(
        postgres_composition,
        rider,
        (
            "payment.intent.create",
            "payment.intent.read_own",
            "payment.attempt.execute",
        ),
    )
    service_identity = existing_identity_ref(callback_identity_id, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service_identity,
        (
            "payment.callback.ingest",
            "payment.trace.read",
        ),
    )
    payment = PaymentOrchestrationService(postgres_composition)
    rider_actor = subject(IdentityType.RIDER, rider.identity_id)
    service_actor = subject(IdentityType.SERVICE, callback_identity_id)

    intent = payment.create_payment_intent(
        rider_actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        ledger_journal_id=context["journal"].journal_id,
        rider_identity_id=rider.identity_id,
        passenger_identity_id=rider.identity_id,
        booker_identity_id=rider.identity_id,
        payer_identity_id=rider.identity_id,
        method=PaymentMethodFamily.CARD,
        idempotency_key=f"intent-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=context["calculation"].calculation_id,
        at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    attempt = payment.create_payment_attempt(
        rider_actor,
        payment_intent_id=intent.payment_intent_id,
        provider_code="provider.refund.test",
        provider_reference=f"ref-{uuid4().hex[:12]}",
        idempotency_key=f"attempt-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=intent.payment_intent_id,
        at=NOW,
    )
    payment.submit_provider_neutral_attempt(
        rider_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        idempotency_key=f"submit-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        provider_code=attempt.provider_code,
        signature_fingerprint="a" * 32,
        callback=CallbackOutcome(
            outcome="authorized",
            provider_event_id=f"evt-{uuid4().hex[:20]}",
            payload={"state": "authorized"},
        ),
        idempotency_key=f"callback-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        provider_code=attempt.provider_code,
        signature_fingerprint="b" * 32,
        callback=CallbackOutcome(
            outcome="capture_pending",
            provider_event_id=f"evt-{uuid4().hex[:20]}",
            payload={"state": "capture_pending"},
        ),
        idempotency_key=f"callback-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    captured = payment.ingest_authenticated_callback_envelope(
        service_actor,
        payment_attempt_id=attempt.payment_attempt_id,
        provider_code=attempt.provider_code,
        signature_fingerprint="c" * 32,
        callback=CallbackOutcome(
            outcome="captured",
            provider_event_id=f"evt-{uuid4().hex[:20]}",
            payload={"state": "captured"},
        ),
        idempotency_key=f"callback-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert captured.state is PaymentAttemptState.CAPTURED
    return context, intent, captured


def test_increment10_refund_authority_state_and_audit(postgres_composition) -> None:
    support = create_identity(postgres_composition, IdentityType.STAFF)
    risk = create_identity(postgres_composition, IdentityType.STAFF)
    finance = create_identity(postgres_composition, IdentityType.STAFF)
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        support,
        ("refund.review.perform", "support.refund.read_status"),
    )
    grant_permissions(
        postgres_composition,
        risk,
        ("refund.investigation.perform", "support.refund.read_status"),
    )
    grant_permissions(
        postgres_composition,
        finance,
        ("refund.approve", "refund.schedule", "refund.trace.read"),
    )
    grant_permissions(
        postgres_composition,
        service_identity,
        (
            "refund.workflow.run",
            "refund.trace.read",
            "payment.callback.ingest",
            "payment.trace.read",
        ),
    )

    context, intent, captured = _captured_attempt(
        postgres_composition,
        callback_identity_id=service_identity.identity_id,
    )
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    grant_permissions(
        postgres_composition,
        rider,
        ("refund.request.create", "refund.trace.read"),
    )
    refund = RefundOrchestrationService(postgres_composition)

    request = refund.request_refund(
        subject(IdentityType.RIDER, rider.identity_id),
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        refund_type=RefundType.FULL_REFUND,
        amount_minor=captured.amount_minor,
        reason_code="refund.customer_request",
        idempotency_key=f"refund-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=captured.payment_attempt_id,
        at=NOW,
    )
    under_review = refund.review_request(
        subject(IdentityType.STAFF, support.identity_id),
        refund_request_id=request.refund_request_id,
        reason_code="refund.review.started",
        idempotency_key=f"review-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert under_review.state is RefundRequestState.UNDER_REVIEW

    refund.investigate_request(
        subject(IdentityType.STAFF, risk.identity_id),
        refund_request_id=request.refund_request_id,
        reason_code="refund.risk.checked",
        evidence_type="support_ticket",
        evidence_reference=f"ticket-{uuid4().hex[:10]}",
        idempotency_key=f"investigate-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    approved = refund.approve_request(
        subject(IdentityType.STAFF, finance.identity_id),
        refund_request_id=request.refund_request_id,
        reason_code="refund.finance.approved",
        idempotency_key=f"approve-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    scheduled = refund.schedule_request(
        subject(IdentityType.STAFF, finance.identity_id),
        refund_request_id=request.refund_request_id,
        reason_code="refund.workflow.scheduled",
        idempotency_key=f"schedule-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert approved.state is RefundRequestState.APPROVED
    assert scheduled.state is RefundRequestState.SCHEDULED

    with pytest.raises(RefundConflict, match="access_denied"):
        refund.complete_request(
            subject(IdentityType.STAFF, support.identity_id),
            refund_request_id=request.refund_request_id,
            reason_code="refund.complete.blocked",
            idempotency_key=f"complete-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )

    completed = refund.complete_request(
        subject(IdentityType.SERVICE, service_identity.identity_id),
        refund_request_id=request.refund_request_id,
        reason_code="refund.complete.planned",
        idempotency_key=f"complete-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert completed.state is RefundRequestState.COMPLETED

    status = refund.refund_status(
        subject(IdentityType.STAFF, support.identity_id),
        refund_request_id=request.refund_request_id,
        at=NOW,
    )
    assert status.request.state is RefundRequestState.COMPLETED
    assert len(status.decisions) >= 5
    assert len(status.authorizations) == 1
    assert len(status.evidence) == 1

    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(refund_events)
            ).scalar_one()
            >= 5
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(refund_outbox)
            ).scalar_one()
            >= 5
        )


def test_increment10_refund_idempotency_conflict(postgres_composition) -> None:
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service_identity,
        ("payment.callback.ingest", "payment.trace.read"),
    )
    context, intent, captured = _captured_attempt(
        postgres_composition,
        callback_identity_id=service_identity.identity_id,
    )
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    grant_permissions(postgres_composition, rider, ("refund.request.create",))
    refund = RefundOrchestrationService(postgres_composition)
    actor = subject(IdentityType.RIDER, rider.identity_id)
    key = f"refund-{uuid4()}"

    first = refund.request_refund(
        actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        refund_type=RefundType.PARTIAL_REFUND,
        amount_minor=max(1, captured.amount_minor - 5),
        reason_code="refund.partial.request",
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=captured.payment_attempt_id,
        at=NOW,
    )
    second = refund.request_refund(
        actor,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        refund_type=RefundType.PARTIAL_REFUND,
        amount_minor=max(1, captured.amount_minor - 5),
        reason_code="refund.partial.request",
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=captured.payment_attempt_id,
        at=NOW,
    )
    assert second.refund_request_id == first.refund_request_id

    with pytest.raises(RefundConflict, match="idempotency_conflict"):
        refund.request_refund(
            actor,
            ride_id=context["ride"].ride_id,
            fare_calculation_id=context["calculation"].calculation_id,
            payment_intent_id=intent.payment_intent_id,
            payment_attempt_id=captured.payment_attempt_id,
            ledger_journal_id=context["journal"].journal_id,
            refund_type=RefundType.PARTIAL_REFUND,
            amount_minor=max(1, captured.amount_minor - 7),
            reason_code="refund.partial.request",
            idempotency_key=key,
            correlation_id=uuid4(),
            causation_id=captured.payment_attempt_id,
            at=NOW,
        )


def test_increment10_refund_reject_is_terminal(postgres_composition) -> None:
    support = create_identity(postgres_composition, IdentityType.STAFF)
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(postgres_composition, support, ("refund.review.perform",))
    grant_permissions(
        postgres_composition,
        service_identity,
        ("payment.callback.ingest", "payment.trace.read"),
    )

    context, intent, captured = _captured_attempt(
        postgres_composition,
        callback_identity_id=service_identity.identity_id,
    )
    rider = existing_identity_ref(context["rider_identity_id"], IdentityType.RIDER)
    grant_permissions(postgres_composition, rider, ("refund.request.create",))
    refund = RefundOrchestrationService(postgres_composition)
    request = refund.request_refund(
        subject(IdentityType.RIDER, rider.identity_id),
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        refund_type=RefundType.SYSTEM_CORRECTION_REQUEST,
        amount_minor=0,
        reason_code="refund.system.correction",
        idempotency_key=f"refund-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=captured.payment_attempt_id,
        at=NOW,
    )
    rejected = refund.reject_request(
        subject(IdentityType.STAFF, support.identity_id),
        refund_request_id=request.refund_request_id,
        reason_code="refund.review.rejected",
        idempotency_key=f"reject-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert rejected.state is RefundRequestState.REJECTED

    with pytest.raises(RefundConflict, match="refund_transition_invalid"):
        refund.review_request(
            subject(IdentityType.STAFF, support.identity_id),
            refund_request_id=request.refund_request_id,
            reason_code="refund.review.retry",
            idempotency_key=f"review-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )
