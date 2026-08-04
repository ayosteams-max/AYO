from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.financial_control.models import (
    FinancialHoldSourceType,
    FinancialHoldState,
)
from BACKEND.identity.models import IdentityType
from BACKEND.payment.models import PaymentAttemptState
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.settlement.authorization import (
    FINANCE_READY_APPROVE_PERMISSION,
    FINANCE_READY_REJECT_PERMISSION,
    RISK_EXCEPTION_INVESTIGATE_PERMISSION,
    SUPPORT_READ_PERMISSION,
    SYSTEM_BATCH_CREATE_PERMISSION,
    SYSTEM_COLLECT_PERMISSION,
    SYSTEM_EVIDENCE_RECORD_PERMISSION,
    SYSTEM_RECONCILE_PERMISSION,
    TRACE_READ_PERMISSION,
    is_service_identity,
)
from BACKEND.settlement.engine import SettlementConflict
from BACKEND.settlement.models import (
    ReconciliationException,
    ReconciliationExceptionType,
    ReconciliationRecord,
    ReconciliationResult,
    ReconciliationTraceability,
    ReconciliationType,
    SettlementApproval,
    SettlementApprovalDecision,
    SettlementBatch,
    SettlementBatchState,
    SettlementEvidenceType,
    SettlementExternalEvidence,
    SettlementHoldEvidence,
    SettlementItem,
)


class SettlementStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch: SettlementBatch
    items: tuple[SettlementItem, ...]
    records: tuple[ReconciliationRecord, ...]
    exceptions: tuple[ReconciliationException, ...]
    approvals: tuple[SettlementApproval, ...] = ()
    hold_evidence: tuple[SettlementHoldEvidence, ...] = ()
    external_evidence: tuple[SettlementExternalEvidence, ...] = ()


class SettlementOrchestrationService:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def create_batch(
        self,
        subject: AuthorizationSubject,
        *,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
        metadata_safe: dict[str, str] | None = None,
    ) -> SettlementBatch:
        self._require_permission(subject, SYSTEM_BATCH_CREATE_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise SettlementConflict("settlement_service_identity_required")
        self._validate_idempotency_key(idempotency_key)

        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.batch.create",
                key=idempotency_key,
                payload={
                    "created_at": at.isoformat(),
                    "metadata_safe": "|".join(
                        f"{key}={value}"
                        for key, value in sorted((metadata_safe or {}).items())
                    ),
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.settlements.get_batch(canonical)
            if existing is not None:
                return existing
            batch = SettlementBatch(
                settlement_batch_id=canonical,
                state=SettlementBatchState.CREATED,
                created_by_identity_id=subject.identity_id,
                created_at=at,
                last_transition_at=at,
                metadata_safe=metadata_safe or {},
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            return unit.settlements.create_batch(batch)

    def collect_item(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        ride_id: UUID,
        fare_calculation_id: UUID,
        payment_intent_id: UUID,
        payment_attempt_id: UUID,
        ledger_journal_id: UUID,
        reconciliation_type: ReconciliationType,
        amount_minor: int,
        refund_request_id: UUID | None,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementItem:
        self._require_permission(subject, SYSTEM_COLLECT_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise SettlementConflict("settlement_service_identity_required")
        self._validate_idempotency_key(idempotency_key)

        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.item.collect",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "ride_id": str(ride_id),
                    "fare_calculation_id": str(fare_calculation_id),
                    "payment_intent_id": str(payment_intent_id),
                    "payment_attempt_id": str(payment_attempt_id),
                    "ledger_journal_id": str(ledger_journal_id),
                    "reconciliation_type": reconciliation_type.value,
                    "amount_minor": str(amount_minor),
                    "refund_request_id": ""
                    if refund_request_id is None
                    else str(refund_request_id),
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.settlements.get_item(canonical)
            if existing is not None:
                return existing

            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state is SettlementBatchState.CREATED:
                batch = unit.settlements.transition_batch(
                    settlement_batch_id=settlement_batch_id,
                    target_state=SettlementBatchState.COLLECTING,
                    at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_batch_id,
                    reason_code="settlement.collecting.started",
                )
            if batch.state is not SettlementBatchState.COLLECTING:
                raise SettlementConflict("settlement_batch_not_collecting")

            intent = unit.payments.get_intent(payment_intent_id, lock=True)
            attempt = unit.payments.get_attempt(payment_attempt_id, lock=True)
            calculation = unit.pricing.get_calculation(fare_calculation_id)
            journal = unit.ledger.get_journal(ledger_journal_id)
            if intent is None or attempt is None:
                raise SettlementConflict("settlement_payment_reference_not_found")
            if calculation is None:
                raise SettlementConflict("settlement_fare_not_found")
            if journal is None:
                raise SettlementConflict("settlement_ledger_not_found")
            if intent.ride_id != ride_id or calculation.ride_id != ride_id:
                raise SettlementConflict("settlement_linkage_conflict")
            if attempt.payment_intent_id != intent.payment_intent_id:
                raise SettlementConflict("settlement_linkage_conflict")
            if intent.traceability.fare_calculation_id != fare_calculation_id:
                raise SettlementConflict("settlement_linkage_conflict")
            if intent.traceability.ledger_journal_id != ledger_journal_id:
                raise SettlementConflict("settlement_linkage_conflict")
            if journal.business_event_id != calculation.calculation_id:
                raise SettlementConflict("settlement_linkage_conflict")
            if attempt.state not in {
                PaymentAttemptState.CAPTURED,
                PaymentAttemptState.OUTCOME_UNKNOWN,
            }:
                raise SettlementConflict("settlement_payment_not_reconcilable")

            if refund_request_id is not None:
                refund = unit.refunds.get_request(refund_request_id, lock=True)
                if refund is None:
                    raise SettlementConflict("settlement_refund_not_found")
                if (
                    refund.ride_id != ride_id
                    or refund.fare_calculation_id != fare_calculation_id
                    or refund.payment_intent_id != payment_intent_id
                    or refund.payment_attempt_id != payment_attempt_id
                    or refund.ledger_journal_id != ledger_journal_id
                ):
                    raise SettlementConflict("settlement_linkage_conflict")

            trace = intent.traceability
            if (
                trace.dispatch_handoff_id is None
                or trace.assignment_id is None
                or trace.active_ride_id is None
                or trace.fare_estimate_id is None
            ):
                raise SettlementConflict("settlement_traceability_incomplete")

            item = SettlementItem(
                settlement_item_id=canonical,
                settlement_batch_id=settlement_batch_id,
                ride_id=ride_id,
                fare_calculation_id=fare_calculation_id,
                payment_intent_id=payment_intent_id,
                payment_attempt_id=payment_attempt_id,
                refund_request_id=refund_request_id,
                ledger_journal_id=ledger_journal_id,
                reconciliation_type=reconciliation_type,
                amount_minor=amount_minor,
                currency=attempt.currency,
                traceability=ReconciliationTraceability(
                    ride_request_id=trace.ride_request_id,
                    dispatch_handoff_id=trace.dispatch_handoff_id,
                    assignment_id=trace.assignment_id,
                    active_ride_id=trace.active_ride_id,
                    fare_estimate_id=trace.fare_estimate_id,
                    fare_calculation_id=trace.fare_calculation_id,
                    ledger_journal_id=ledger_journal_id,
                ),
                created_at=at,
            )
            return unit.settlements.add_item(item)

    def reconcile_item(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        settlement_item_id: UUID,
        result: ReconciliationResult,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
        decision_safe: dict[str, str] | None = None,
    ) -> ReconciliationRecord:
        self._require_permission(subject, SYSTEM_RECONCILE_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise SettlementConflict("settlement_service_identity_required")
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.item.reconcile",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "settlement_item_id": str(settlement_item_id),
                    "result": result.value,
                    "reason_code": reason_code,
                },
                response_reference=settlement_item_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state in {
                SettlementBatchState.CREATED,
                SettlementBatchState.COLLECTING,
            }:
                batch = unit.settlements.transition_batch(
                    settlement_batch_id=settlement_batch_id,
                    target_state=SettlementBatchState.RECONCILING,
                    at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_item_id,
                    reason_code="settlement.reconciling.started",
                )
            if batch.state is not SettlementBatchState.RECONCILING:
                raise SettlementConflict("settlement_batch_not_reconciling")

            item = unit.settlements.get_item(settlement_item_id, lock=True)
            if item is None or item.settlement_batch_id != settlement_batch_id:
                raise SettlementConflict("settlement_item_not_found")

            record = unit.settlements.append_reconciliation_record(
                ReconciliationRecord(
                    settlement_batch_id=settlement_batch_id,
                    settlement_item_id=settlement_item_id,
                    reconciliation_type=item.reconciliation_type,
                    result=result,
                    reason_code=reason_code,
                    decision_safe=decision_safe or {},
                    recorded_by_identity_id=subject.identity_id,
                    recorded_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_item_id,
                )
            )
            if result in {
                ReconciliationResult.MISMATCH,
                ReconciliationResult.MISSING,
                ReconciliationResult.DUPLICATE,
                ReconciliationResult.MANUAL_REVIEW_REQUIRED,
            }:
                unit.settlements.append_exception(
                    ReconciliationException(
                        settlement_batch_id=settlement_batch_id,
                        settlement_item_id=settlement_item_id,
                        exception_type=self._exception_from_result(result),
                        exception_state=SettlementBatchState.EXCEPTION,
                        details_safe={"reason_code": reason_code},
                        raised_by_identity_id=subject.identity_id,
                        raised_at=at,
                        correlation_id=correlation_id,
                        causation_id=settlement_item_id,
                    )
                )
                unit.settlements.transition_batch(
                    settlement_batch_id=settlement_batch_id,
                    target_state=SettlementBatchState.EXCEPTION,
                    at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_item_id,
                    reason_code="settlement.exception.raised",
                )
            return record

    def mark_balanced(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementBatch:
        self._require_permission(subject, SYSTEM_RECONCILE_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise SettlementConflict("settlement_service_identity_required")
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.batch.balanced",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "reason_code": reason_code,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state is not SettlementBatchState.RECONCILING:
                raise SettlementConflict("settlement_batch_not_reconciling")
            if unit.settlements.list_exceptions(settlement_batch_id):
                raise SettlementConflict("settlement_batch_has_exceptions")
            if not unit.settlements.list_items(settlement_batch_id):
                raise SettlementConflict("settlement_batch_no_items")
            return unit.settlements.transition_batch(
                settlement_batch_id=settlement_batch_id,
                target_state=SettlementBatchState.BALANCED,
                at=at,
                correlation_id=correlation_id,
                causation_id=settlement_batch_id,
                reason_code=reason_code,
            )

    def approve_settlement_readiness(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementApproval:
        self._require_permission(subject, FINANCE_READY_APPROVE_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.batch.finance_approve",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "reason_code": reason_code,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state is not SettlementBatchState.BALANCED:
                raise SettlementConflict("settlement_batch_not_balanced")
            if subject.identity_type not in {
                IdentityType.STAFF,
                IdentityType.ADMINISTRATOR,
            }:
                raise SettlementConflict("settlement_human_approval_required")
            if batch.created_by_identity_id == subject.identity_id:
                raise SettlementConflict("settlement_maker_checker_required")
            return unit.settlements.append_approval(
                SettlementApproval(
                    settlement_batch_id=settlement_batch_id,
                    decision=SettlementApprovalDecision.APPROVED,
                    reason_code=reason_code,
                    prepared_by_identity_id=batch.created_by_identity_id,
                    decided_by_identity_id=subject.identity_id,
                    decided_by_actor_type=subject.actor_type.value,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_batch_id,
                )
            )

    def reject_settlement_readiness(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementApproval:
        self._require_permission(subject, FINANCE_READY_REJECT_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.batch.finance_reject",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "reason_code": reason_code,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if subject.identity_type not in {
                IdentityType.STAFF,
                IdentityType.ADMINISTRATOR,
            }:
                raise SettlementConflict("settlement_human_approval_required")
            if batch.created_by_identity_id == subject.identity_id:
                raise SettlementConflict("settlement_maker_checker_required")
            return unit.settlements.append_approval(
                SettlementApproval(
                    settlement_batch_id=settlement_batch_id,
                    decision=SettlementApprovalDecision.REJECTED,
                    reason_code=reason_code,
                    prepared_by_identity_id=batch.created_by_identity_id,
                    decided_by_identity_id=subject.identity_id,
                    decided_by_actor_type=subject.actor_type.value,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_batch_id,
                )
            )

    def mark_ready_for_settlement(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementBatch:
        self._require_permission(subject, SYSTEM_RECONCILE_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise SettlementConflict("settlement_service_identity_required")
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.batch.ready",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "reason_code": reason_code,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state is not SettlementBatchState.BALANCED:
                raise SettlementConflict("settlement_batch_not_balanced")
            approvals = unit.settlements.list_approvals(settlement_batch_id)
            if (
                not approvals
                or approvals[-1].decision is not SettlementApprovalDecision.APPROVED
            ):
                raise SettlementConflict("settlement_finance_approval_required")
            holds = unit.financial_holds.list_holds_for_source(
                source_type=FinancialHoldSourceType.SETTLEMENT_BATCH,
                source_id=settlement_batch_id,
            )
            blocking = next(
                (
                    hold
                    for hold in reversed(holds)
                    if hold.state
                    in {
                        FinancialHoldState.CREATED,
                        FinancialHoldState.ACTIVE,
                        FinancialHoldState.UNDER_REVIEW,
                        FinancialHoldState.ESCALATED,
                    }
                ),
                None,
            )
            unit.settlements.append_hold_evidence(
                SettlementHoldEvidence(
                    settlement_batch_id=settlement_batch_id,
                    financial_hold_id=None if blocking is None else blocking.hold_id,
                    hold_state="none" if blocking is None else blocking.state.value,
                    blocks_readiness=blocking is not None,
                    evaluated_by_identity_id=subject.identity_id,
                    evaluated_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_batch_id,
                )
            )
            if blocking is not None:
                raise SettlementConflict("settlement_blocked_by_financial_hold")
            return unit.settlements.transition_batch(
                settlement_batch_id=settlement_batch_id,
                target_state=SettlementBatchState.READY_FOR_SETTLEMENT,
                at=at,
                correlation_id=correlation_id,
                causation_id=settlement_batch_id,
                reason_code=reason_code,
            )

    def investigate_exception(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        settlement_item_id: UUID,
        exception_type: ReconciliationExceptionType,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementBatch:
        self._require_permission(subject, RISK_EXCEPTION_INVESTIGATE_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.exception.investigate",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "settlement_item_id": str(settlement_item_id),
                    "exception_type": exception_type.value,
                    "reason_code": reason_code,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state is not SettlementBatchState.EXCEPTION:
                raise SettlementConflict("settlement_batch_not_exception")
            unit.settlements.append_exception(
                ReconciliationException(
                    settlement_batch_id=settlement_batch_id,
                    settlement_item_id=settlement_item_id,
                    exception_type=exception_type,
                    exception_state=SettlementBatchState.MANUAL_REVIEW,
                    details_safe={"reason_code": reason_code},
                    raised_by_identity_id=subject.identity_id,
                    raised_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_item_id,
                )
            )
            return unit.settlements.transition_batch(
                settlement_batch_id=settlement_batch_id,
                target_state=SettlementBatchState.MANUAL_REVIEW,
                at=at,
                correlation_id=correlation_id,
                causation_id=settlement_item_id,
                reason_code=reason_code,
            )

    def resolve_exception(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        settlement_item_id: UUID,
        resolution_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementBatch:
        self._require_permission(subject, RISK_EXCEPTION_INVESTIGATE_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)

        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="settlement.exception.resolve",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "settlement_item_id": str(settlement_item_id),
                    "resolution_code": resolution_code,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if batch.state is not SettlementBatchState.MANUAL_REVIEW:
                raise SettlementConflict("settlement_batch_not_manual_review")
            unit.settlements.append_exception(
                ReconciliationException(
                    settlement_batch_id=settlement_batch_id,
                    settlement_item_id=settlement_item_id,
                    exception_type=ReconciliationExceptionType.MANUAL_INVESTIGATION,
                    exception_state=SettlementBatchState.RESOLVED,
                    details_safe={"resolution_code": resolution_code},
                    raised_by_identity_id=subject.identity_id,
                    raised_at=at,
                    resolution_code=resolution_code,
                    resolved_by_identity_id=subject.identity_id,
                    resolved_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_item_id,
                )
            )
            return unit.settlements.transition_batch(
                settlement_batch_id=settlement_batch_id,
                target_state=SettlementBatchState.RESOLVED,
                at=at,
                correlation_id=correlation_id,
                causation_id=settlement_item_id,
                reason_code=resolution_code,
            )

    def settlement_status(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        at: datetime,
    ) -> SettlementStatus:
        with self._composition.unit_of_work() as unit:
            batch = unit.settlements.get_batch(settlement_batch_id)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            self._require_read(subject, at=at)
            return SettlementStatus(
                batch=batch,
                items=unit.settlements.list_items(settlement_batch_id),
                records=unit.settlements.list_reconciliation_records(
                    settlement_batch_id
                ),
                exceptions=unit.settlements.list_exceptions(settlement_batch_id),
                approvals=unit.settlements.list_approvals(settlement_batch_id),
                hold_evidence=unit.settlements.list_hold_evidence(settlement_batch_id),
                external_evidence=unit.settlements.list_external_evidence(
                    settlement_batch_id
                ),
            )

    def record_external_evidence(
        self,
        subject: AuthorizationSubject,
        *,
        settlement_batch_id: UUID,
        evidence_type: SettlementEvidenceType,
        provider_code: str,
        provider_reference: str,
        evidence_fingerprint: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> SettlementExternalEvidence:
        self._require_permission(subject, SYSTEM_EVIDENCE_RECORD_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise SettlementConflict("settlement_service_identity_required")
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.settlements.reserve_idempotency(
                actor_id=subject.identity_id,
                operation=f"settlement.evidence.{evidence_type.value}",
                key=idempotency_key,
                payload={
                    "settlement_batch_id": str(settlement_batch_id),
                    "provider_code": provider_code,
                    "provider_reference": provider_reference,
                    "evidence_fingerprint": evidence_fingerprint,
                },
                response_reference=settlement_batch_id,
                at=at,
            )
            batch = unit.settlements.get_batch(settlement_batch_id, lock=True)
            if batch is None:
                raise SettlementConflict("settlement_batch_not_found")
            if evidence_type is SettlementEvidenceType.CONFIRMATION:
                prior = unit.settlements.list_external_evidence(settlement_batch_id)
                if not any(
                    item.evidence_type is SettlementEvidenceType.SUBMISSION
                    and item.provider_code == provider_code
                    for item in prior
                ):
                    raise SettlementConflict("settlement_submission_evidence_required")
            return unit.settlements.append_external_evidence(
                SettlementExternalEvidence(
                    settlement_batch_id=settlement_batch_id,
                    evidence_type=evidence_type,
                    provider_code=provider_code,
                    provider_reference=provider_reference,
                    evidence_fingerprint=evidence_fingerprint,
                    recorded_by_identity_id=subject.identity_id,
                    recorded_at=at,
                    correlation_id=correlation_id,
                    causation_id=settlement_batch_id,
                )
            )

    def _require_permission(
        self, subject: AuthorizationSubject, permission: str, *, at: datetime
    ) -> None:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, permission, at=at
            ):
                raise SettlementConflict("access_denied")

    def _require_read(self, subject: AuthorizationSubject, *, at: datetime) -> None:
        with self._composition.unit_of_work() as unit:
            if unit.authorization.has_permission(
                subject.identity_id, SUPPORT_READ_PERMISSION, at=at
            ) or unit.authorization.has_permission(
                subject.identity_id, TRACE_READ_PERMISSION, at=at
            ):
                return
        raise SettlementConflict("settlement_status_not_found")

    @staticmethod
    def _validate_idempotency_key(value: str) -> None:
        if not 16 <= len(value) <= 128:
            raise SettlementConflict("idempotency_key_invalid")

    @staticmethod
    def _exception_from_result(
        result: ReconciliationResult,
    ) -> ReconciliationExceptionType:
        return {
            ReconciliationResult.MISMATCH: ReconciliationExceptionType.AMOUNT_MISMATCH,
            ReconciliationResult.MISSING: ReconciliationExceptionType.MISSING_CALLBACK,
            ReconciliationResult.DUPLICATE: ReconciliationExceptionType.DUPLICATE_PAYMENT,
            ReconciliationResult.MANUAL_REVIEW_REQUIRED: ReconciliationExceptionType.MANUAL_INVESTIGATION,
            ReconciliationResult.MATCHED: ReconciliationExceptionType.UNKNOWN_OUTCOME,
            ReconciliationResult.PARTIALLY_MATCHED: ReconciliationExceptionType.REFUND_MISMATCH,
        }[result]
