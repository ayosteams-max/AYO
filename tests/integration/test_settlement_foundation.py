from datetime import timedelta
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from BACKEND.financial_control.application import FinancialHoldApplicationService
from BACKEND.financial_control.models import (
    FinancialHoldCreateCommand,
    FinancialHoldReasonCode,
    FinancialHoldSourceType,
    FinancialHoldState,
    FinancialHoldTransitionCommand,
    FinancialHoldType,
    HoldReason,
)
from BACKEND.identity.models import IdentityType
from BACKEND.payment.application import CallbackOutcome, PaymentOrchestrationService
from BACKEND.payment.models import PaymentAttemptState, PaymentMethodFamily
from BACKEND.persistence.tables import (
    ledger_entries,
    payment_attempts,
    refund_requests,
    wallet_lineage_entries,
)
from BACKEND.refund.application import RefundOrchestrationService
from BACKEND.refund.models import RefundType
from BACKEND.settlement.application import SettlementOrchestrationService
from BACKEND.settlement.engine import SettlementConflict
from BACKEND.settlement.models import (
    ReconciliationExceptionType,
    ReconciliationResult,
    ReconciliationType,
    SettlementApprovalDecision,
    SettlementBatchState,
    SettlementEvidenceType,
)
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
            "refund.request.create",
            "refund.trace.read",
        ),
    )
    service_identity = existing_identity_ref(callback_identity_id, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service_identity,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
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
        provider_code="provider.settlement.test",
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
    return context, rider, intent, captured


def test_increment11_settlement_authority_and_ready_flow(postgres_composition) -> None:
    support = create_identity(postgres_composition, IdentityType.STAFF)
    finance = create_identity(postgres_composition, IdentityType.STAFF)
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)

    grant_permissions(
        postgres_composition,
        support,
        ("support.settlement.read_status",),
    )
    grant_permissions(
        postgres_composition,
        finance,
        ("settlement.ready.approve", "settlement.trace.read"),
    )

    context, rider, intent, captured = _captured_attempt(
        postgres_composition,
        callback_identity_id=service_identity.identity_id,
    )
    grant_permissions(
        postgres_composition,
        service_identity,
        (
            "financial.hold.create",
            "financial.hold.review",
            "financial.hold.release",
            "settlement.ready.approve",
            "settlement.evidence.record",
        ),
    )
    refund = RefundOrchestrationService(postgres_composition)
    refund_request = refund.request_refund(
        subject(IdentityType.RIDER, rider.identity_id),
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        refund_type=RefundType.PARTIAL_REFUND,
        amount_minor=max(1, captured.amount_minor - 5),
        reason_code="refund.partial.request",
        idempotency_key=f"refund-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=captured.payment_attempt_id,
        at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        authority_before = {
            "ledger": tuple(unit.connection.execute(select(ledger_entries)).all()),
            "wallet": tuple(
                unit.connection.execute(select(wallet_lineage_entries)).all()
            ),
            "payment": tuple(unit.connection.execute(select(payment_attempts)).all()),
            "refund": tuple(unit.connection.execute(select(refund_requests)).all()),
        }

    settlement = SettlementOrchestrationService(postgres_composition)
    service_actor = subject(IdentityType.SERVICE, service_identity.identity_id)
    support_actor = subject(IdentityType.STAFF, support.identity_id)

    batch = settlement.create_batch(
        service_actor,
        idempotency_key=f"batch-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    item = settlement.collect_item(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        reconciliation_type=ReconciliationType.SETTLEMENT_RECONCILIATION,
        amount_minor=captured.amount_minor,
        refund_request_id=refund_request.refund_request_id,
        idempotency_key=f"collect-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    settlement.reconcile_item(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        settlement_item_id=item.settlement_item_id,
        result=ReconciliationResult.MATCHED,
        reason_code="settlement.reconcile.matched",
        idempotency_key=f"reconcile-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    balanced = settlement.mark_balanced(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        reason_code="settlement.batch.balanced",
        idempotency_key=f"balanced-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert balanced.state is SettlementBatchState.BALANCED

    with pytest.raises(SettlementConflict, match="settlement_human_approval_required"):
        settlement.approve_settlement_readiness(
            service_actor,
            settlement_batch_id=batch.settlement_batch_id,
            reason_code="settlement.finance.ai_forbidden",
            idempotency_key=f"approve-service-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )

    approval = settlement.approve_settlement_readiness(
        subject(IdentityType.STAFF, finance.identity_id),
        settlement_batch_id=batch.settlement_batch_id,
        reason_code="settlement.finance.approved",
        idempotency_key=f"approve-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert approval.decision is SettlementApprovalDecision.APPROVED

    holds = FinancialHoldApplicationService(postgres_composition)
    hold = holds.create_hold(
        service_actor,
        FinancialHoldCreateCommand(
            hold_type=FinancialHoldType.SETTLEMENT,
            source_type=FinancialHoldSourceType.SETTLEMENT_BATCH,
            source_id=batch.settlement_batch_id,
            reason=HoldReason(
                reason_code=FinancialHoldReasonCode.SETTLEMENT_EXCEPTION_REVIEW,
                reason_detail=None,
            ),
            idempotency_key=f"settlement-hold-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=batch.settlement_batch_id,
            occurred_at=NOW,
        ),
    ).hold

    with pytest.raises(
        SettlementConflict, match="settlement_blocked_by_financial_hold"
    ):
        settlement.mark_ready_for_settlement(
            service_actor,
            settlement_batch_id=batch.settlement_batch_id,
            reason_code="settlement.ready.hold_blocked",
            idempotency_key=f"ready-blocked-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )

    hold = holds.transition_hold(
        service_actor,
        hold_id=hold.hold_id,
        command=FinancialHoldTransitionCommand(
            target_state=FinancialHoldState.ACTIVE,
            reason=HoldReason(
                reason_code=FinancialHoldReasonCode.SETTLEMENT_EXCEPTION_REVIEW,
                reason_detail=None,
            ),
            idempotency_key=f"settlement-hold-active-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=hold.hold_id,
            occurred_at=NOW,
        ),
    ).hold
    holds.transition_hold(
        service_actor,
        hold_id=hold.hold_id,
        command=FinancialHoldTransitionCommand(
            target_state=FinancialHoldState.RELEASED,
            reason=HoldReason(
                reason_code=FinancialHoldReasonCode.SETTLEMENT_EXCEPTION_REVIEW,
                reason_detail=None,
            ),
            idempotency_key=f"settlement-hold-release-{uuid4()}",
            correlation_id=uuid4(),
            causation_id=hold.hold_id,
            occurred_at=NOW,
        ),
    )

    with pytest.raises(SettlementConflict, match="access_denied"):
        settlement.mark_ready_for_settlement(
            support_actor,
            settlement_batch_id=batch.settlement_batch_id,
            reason_code="settlement.ready.forbidden",
            idempotency_key=f"ready-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )

    ready = settlement.mark_ready_for_settlement(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        reason_code="settlement.ready.marked",
        idempotency_key=f"ready-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert ready.state is SettlementBatchState.READY_FOR_SETTLEMENT

    with pytest.raises(
        SettlementConflict, match="settlement_submission_evidence_required"
    ):
        settlement.record_external_evidence(
            service_actor,
            settlement_batch_id=batch.settlement_batch_id,
            evidence_type=SettlementEvidenceType.CONFIRMATION,
            provider_code="provider.test",
            provider_reference=f"confirm-{uuid4()}",
            evidence_fingerprint="a" * 64,
            idempotency_key=f"evidence-confirm-early-{uuid4()}",
            correlation_id=uuid4(),
            at=NOW,
        )
    settlement.record_external_evidence(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        evidence_type=SettlementEvidenceType.SUBMISSION,
        provider_code="provider.test",
        provider_reference=f"submit-{uuid4()}",
        evidence_fingerprint="b" * 64,
        idempotency_key=f"evidence-submit-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    settlement.record_external_evidence(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        evidence_type=SettlementEvidenceType.CONFIRMATION,
        provider_code="provider.test",
        provider_reference=f"confirm-{uuid4()}",
        evidence_fingerprint="c" * 64,
        idempotency_key=f"evidence-confirm-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )

    status = settlement.settlement_status(
        support_actor,
        settlement_batch_id=batch.settlement_batch_id,
        at=NOW,
    )
    assert status.batch.state is SettlementBatchState.READY_FOR_SETTLEMENT
    assert len(status.items) == 1
    assert status.approvals[-1].decision is SettlementApprovalDecision.APPROVED
    assert status.hold_evidence[-1].blocks_readiness is False
    assert len(status.external_evidence) == 2

    started = perf_counter()
    for _ in range(50):
        assert (
            settlement.settlement_status(
                support_actor,
                settlement_batch_id=batch.settlement_batch_id,
                at=NOW,
            ).batch.state
            is SettlementBatchState.READY_FOR_SETTLEMENT
        )
    assert perf_counter() - started < 2.0

    with postgres_composition.unit_of_work() as unit:
        authority_after = {
            "ledger": tuple(unit.connection.execute(select(ledger_entries)).all()),
            "wallet": tuple(
                unit.connection.execute(select(wallet_lineage_entries)).all()
            ),
            "payment": tuple(unit.connection.execute(select(payment_attempts)).all()),
            "refund": tuple(unit.connection.execute(select(refund_requests)).all()),
        }
    assert authority_after == authority_before


def test_increment11_settlement_exception_workflow(postgres_composition) -> None:
    risk = create_identity(postgres_composition, IdentityType.STAFF)
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        risk,
        ("settlement.exception.investigate", "settlement.trace.read"),
    )

    context, _, intent, captured = _captured_attempt(
        postgres_composition,
        callback_identity_id=service_identity.identity_id,
    )
    settlement = SettlementOrchestrationService(postgres_composition)
    service_actor = subject(IdentityType.SERVICE, service_identity.identity_id)

    batch = settlement.create_batch(
        service_actor,
        idempotency_key=f"batch-{uuid4()}",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    item = settlement.collect_item(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        ride_id=context["ride"].ride_id,
        fare_calculation_id=context["calculation"].calculation_id,
        payment_intent_id=intent.payment_intent_id,
        payment_attempt_id=captured.payment_attempt_id,
        ledger_journal_id=context["journal"].journal_id,
        reconciliation_type=ReconciliationType.PAYMENT_RECONCILIATION,
        amount_minor=captured.amount_minor,
        refund_request_id=None,
        idempotency_key=f"collect-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    settlement.reconcile_item(
        service_actor,
        settlement_batch_id=batch.settlement_batch_id,
        settlement_item_id=item.settlement_item_id,
        result=ReconciliationResult.MISMATCH,
        reason_code="settlement.reconcile.mismatch",
        idempotency_key=f"reconcile-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )

    manual_review = settlement.investigate_exception(
        subject(IdentityType.STAFF, risk.identity_id),
        settlement_batch_id=batch.settlement_batch_id,
        settlement_item_id=item.settlement_item_id,
        exception_type=ReconciliationExceptionType.AMOUNT_MISMATCH,
        reason_code="settlement.exception.investigating",
        idempotency_key=f"investigate-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert manual_review.state is SettlementBatchState.MANUAL_REVIEW

    resolved = settlement.resolve_exception(
        subject(IdentityType.STAFF, risk.identity_id),
        settlement_batch_id=batch.settlement_batch_id,
        settlement_item_id=item.settlement_item_id,
        resolution_code="settlement.exception.resolved",
        idempotency_key=f"resolve-{uuid4()}",
        correlation_id=uuid4(),
        at=NOW,
    )
    assert resolved.state is SettlementBatchState.RESOLVED


def test_increment11_settlement_idempotency_conflict(postgres_composition) -> None:
    service_identity = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service_identity,
        ("settlement.batch.create",),
    )
    settlement = SettlementOrchestrationService(postgres_composition)
    actor = subject(IdentityType.SERVICE, service_identity.identity_id)
    key = f"batch-{uuid4()}"

    first = settlement.create_batch(
        actor,
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
        metadata_safe={"a": "1"},
    )
    second = settlement.create_batch(
        actor,
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
        metadata_safe={"a": "1"},
    )
    assert first.settlement_batch_id == second.settlement_batch_id

    with pytest.raises(SettlementConflict, match="idempotency_conflict"):
        settlement.create_batch(
            actor,
            idempotency_key=key,
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
            metadata_safe={"a": "2"},
        )
