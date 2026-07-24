from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.payment.models import PaymentAttemptState
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.refund.authorization import (
    CUSTOMER_CREATE_PERMISSION,
    FINANCE_APPROVAL_PERMISSION,
    RISK_INVESTIGATION_PERMISSION,
    SCHEDULING_PERMISSION,
    SUPPORT_READ_PERMISSION,
    SUPPORT_REVIEW_PERMISSION,
    TRACE_READ_PERMISSION,
    WORKFLOW_COMPLETION_PERMISSION,
    is_customer_identity,
    is_service_identity,
)
from BACKEND.refund.engine import RefundConflict
from BACKEND.refund.models import (
    RefundAuthorization,
    RefundAuthorizationType,
    RefundDecision,
    RefundDecisionType,
    RefundEvidence,
    RefundRequest,
    RefundRequestState,
    RefundTraceability,
    RefundType,
)


class RefundStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: RefundRequest
    decisions: tuple[RefundDecision, ...]
    authorizations: tuple[RefundAuthorization, ...]
    evidence: tuple[RefundEvidence, ...]


class RefundRideHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_id: UUID
    statuses: tuple[RefundStatus, ...]


class RefundOrchestrationService:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def request_refund(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        fare_calculation_id: UUID,
        payment_intent_id: UUID,
        payment_attempt_id: UUID,
        ledger_journal_id: UUID,
        refund_type: RefundType,
        amount_minor: int,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
        metadata_safe: dict[str, str] | None = None,
    ) -> RefundRequest:
        self._require_permission(subject, CUSTOMER_CREATE_PERMISSION, at=at)
        if not is_customer_identity(subject.identity_type):
            raise RefundConflict("refund_customer_identity_required")
        self._validate_idempotency_key(idempotency_key)

        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.create",
                key=idempotency_key,
                payload={
                    "ride_id": str(ride_id),
                    "fare_calculation_id": str(fare_calculation_id),
                    "payment_intent_id": str(payment_intent_id),
                    "payment_attempt_id": str(payment_attempt_id),
                    "ledger_journal_id": str(ledger_journal_id),
                    "refund_type": refund_type.value,
                    "amount_minor": str(amount_minor),
                    "reason_code": reason_code,
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.refunds.get_request(canonical)
            if existing is not None:
                return existing

            intent = unit.payments.get_intent(payment_intent_id, lock=True)
            attempt = unit.payments.get_attempt(payment_attempt_id, lock=True)
            calculation = unit.pricing.get_calculation(fare_calculation_id)
            journal = unit.ledger.get_journal(ledger_journal_id)

            if intent is None:
                raise RefundConflict("payment_intent_not_found")
            if attempt is None:
                raise RefundConflict("payment_attempt_not_found")
            if attempt.payment_intent_id != intent.payment_intent_id:
                raise RefundConflict("refund_linkage_conflict")
            if attempt.state is not PaymentAttemptState.CAPTURED:
                raise RefundConflict("refund_requires_captured_payment")
            if intent.ride_id != ride_id:
                raise RefundConflict("refund_linkage_conflict")
            if intent.rider_identity_id != subject.identity_id:
                raise RefundConflict("refund_requester_not_owner")
            if intent.traceability.fare_calculation_id != fare_calculation_id:
                raise RefundConflict("refund_linkage_conflict")
            if intent.traceability.ledger_journal_id != ledger_journal_id:
                raise RefundConflict("refund_linkage_conflict")
            if calculation is None:
                raise RefundConflict("fare_calculation_not_found")
            if journal is None:
                raise RefundConflict("ledger_journal_not_found")
            if journal.business_event_id != calculation.calculation_id:
                raise RefundConflict("ledger_lineage_conflict")

            self._validate_request_amount(
                refund_type=refund_type,
                amount_minor=amount_minor,
                payment_amount_minor=attempt.amount_minor,
            )

            request = RefundRequest(
                refund_request_id=canonical,
                ride_id=ride_id,
                fare_calculation_id=fare_calculation_id,
                payment_intent_id=payment_intent_id,
                payment_attempt_id=payment_attempt_id,
                ledger_journal_id=ledger_journal_id,
                refund_type=refund_type,
                state=RefundRequestState.REQUESTED,
                amount_minor=amount_minor,
                currency=attempt.currency,
                reason_code=reason_code,
                requested_by_identity_id=subject.identity_id,
                requested_at=at,
                last_transition_at=at,
                correlation_id=correlation_id,
                causation_id=causation_id,
                metadata_safe=metadata_safe or {},
                traceability=RefundTraceability(
                    ride_request_id=intent.traceability.ride_request_id,
                    dispatch_handoff_id=intent.traceability.dispatch_handoff_id,
                    assignment_id=intent.traceability.assignment_id,
                    active_ride_id=intent.traceability.active_ride_id,
                    fare_estimate_id=intent.traceability.fare_estimate_id,
                    fare_calculation_id=intent.traceability.fare_calculation_id,
                    ledger_journal_id=ledger_journal_id,
                ),
            )
            created = unit.refunds.create_request(request)
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=created.refund_request_id,
                    decision_type=RefundDecisionType.REVIEW,
                    decision_outcome="requested",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                )
            )
            return created

    def review_request(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> RefundRequest:
        self._require_permission(subject, SUPPORT_REVIEW_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.review",
                key=idempotency_key,
                payload={
                    "refund_request_id": str(refund_request_id),
                    "reason_code": reason_code,
                },
                response_reference=refund_request_id,
                at=at,
            )
            changed = unit.refunds.transition_request(
                refund_request_id=refund_request_id,
                target_state=RefundRequestState.UNDER_REVIEW,
                at=at,
                correlation_id=correlation_id,
                causation_id=refund_request_id,
                reason_code=reason_code,
            )
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=changed.refund_request_id,
                    decision_type=RefundDecisionType.REVIEW,
                    decision_outcome="under_review",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            return changed

    def investigate_request(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        reason_code: str,
        evidence_type: str,
        evidence_reference: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> None:
        self._require_permission(subject, RISK_INVESTIGATION_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.investigate",
                key=idempotency_key,
                payload={
                    "refund_request_id": str(refund_request_id),
                    "reason_code": reason_code,
                    "evidence_type": evidence_type,
                    "evidence_reference": evidence_reference,
                },
                response_reference=refund_request_id,
                at=at,
            )
            request = unit.refunds.get_request(refund_request_id, lock=True)
            if request is None:
                raise RefundConflict("refund_request_not_found")
            if request.state is not RefundRequestState.UNDER_REVIEW:
                raise RefundConflict("refund_investigation_state_invalid")
            unit.refunds.append_evidence(
                RefundEvidence(
                    refund_request_id=refund_request_id,
                    evidence_type=evidence_type,
                    evidence_reference=evidence_reference,
                    recorded_by_identity_id=subject.identity_id,
                    safe_metadata={"reason_code": reason_code},
                    recorded_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=refund_request_id,
                    decision_type=RefundDecisionType.INVESTIGATION,
                    decision_outcome="investigated",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )

    def approve_request(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> RefundRequest:
        self._require_permission(subject, FINANCE_APPROVAL_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.approve",
                key=idempotency_key,
                payload={
                    "refund_request_id": str(refund_request_id),
                    "reason_code": reason_code,
                },
                response_reference=refund_request_id,
                at=at,
            )
            changed = unit.refunds.transition_request(
                refund_request_id=refund_request_id,
                target_state=RefundRequestState.APPROVED,
                at=at,
                correlation_id=correlation_id,
                causation_id=refund_request_id,
                reason_code=reason_code,
            )
            unit.refunds.append_authorization(
                RefundAuthorization(
                    refund_request_id=refund_request_id,
                    authorization_type=RefundAuthorizationType.FINANCE_APPROVAL,
                    authorized_by_identity_id=subject.identity_id,
                    authority_permission=FINANCE_APPROVAL_PERMISSION,
                    reason_code=reason_code,
                    authorized_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=refund_request_id,
                    decision_type=RefundDecisionType.APPROVAL,
                    decision_outcome="approved",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            return changed

    def schedule_request(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> RefundRequest:
        self._require_permission(subject, SCHEDULING_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.schedule",
                key=idempotency_key,
                payload={
                    "refund_request_id": str(refund_request_id),
                    "reason_code": reason_code,
                },
                response_reference=refund_request_id,
                at=at,
            )
            changed = unit.refunds.transition_request(
                refund_request_id=refund_request_id,
                target_state=RefundRequestState.SCHEDULED,
                at=at,
                correlation_id=correlation_id,
                causation_id=refund_request_id,
                reason_code=reason_code,
            )
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=refund_request_id,
                    decision_type=RefundDecisionType.SCHEDULING,
                    decision_outcome="scheduled",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            return changed

    def complete_request(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> RefundRequest:
        self._require_permission(subject, WORKFLOW_COMPLETION_PERMISSION, at=at)
        if not is_service_identity(subject.identity_type):
            raise RefundConflict("refund_completion_requires_service")
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.complete",
                key=idempotency_key,
                payload={
                    "refund_request_id": str(refund_request_id),
                    "reason_code": reason_code,
                },
                response_reference=refund_request_id,
                at=at,
            )
            changed = unit.refunds.transition_request(
                refund_request_id=refund_request_id,
                target_state=RefundRequestState.COMPLETED,
                at=at,
                correlation_id=correlation_id,
                causation_id=refund_request_id,
                reason_code=reason_code,
            )
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=refund_request_id,
                    decision_type=RefundDecisionType.COMPLETION,
                    decision_outcome="completed",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            return changed

    def reject_request(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> RefundRequest:
        self._require_permission(subject, SUPPORT_REVIEW_PERMISSION, at=at)
        self._validate_idempotency_key(idempotency_key)
        with self._composition.unit_of_work() as unit:
            unit.refunds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="refund.request.reject",
                key=idempotency_key,
                payload={
                    "refund_request_id": str(refund_request_id),
                    "reason_code": reason_code,
                },
                response_reference=refund_request_id,
                at=at,
            )
            changed = unit.refunds.transition_request(
                refund_request_id=refund_request_id,
                target_state=RefundRequestState.REJECTED,
                at=at,
                correlation_id=correlation_id,
                causation_id=refund_request_id,
                reason_code=reason_code,
            )
            unit.refunds.append_decision(
                RefundDecision(
                    refund_request_id=refund_request_id,
                    decision_type=RefundDecisionType.REJECTION,
                    decision_outcome="rejected",
                    decided_by_identity_id=subject.identity_id,
                    reason_code=reason_code,
                    decided_at=at,
                    correlation_id=correlation_id,
                    causation_id=refund_request_id,
                )
            )
            return changed

    def refund_status(
        self,
        subject: AuthorizationSubject,
        *,
        refund_request_id: UUID,
        at: datetime,
    ) -> RefundStatus:
        with self._composition.unit_of_work() as unit:
            request = unit.refunds.get_request(refund_request_id)
            if request is None:
                raise RefundConflict("refund_request_not_found")
            self._require_read(subject, request=request, at=at)
            return RefundStatus(
                request=request,
                decisions=unit.refunds.list_decisions(refund_request_id),
                authorizations=unit.refunds.list_authorizations(refund_request_id),
                evidence=unit.refunds.list_evidence(refund_request_id),
            )

    def refund_history_by_ride(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        at: datetime,
    ) -> RefundRideHistory:
        with self._composition.unit_of_work() as unit:
            requests = unit.refunds.list_requests_for_ride(ride_id)
            if not requests:
                raise RefundConflict("refund_history_not_found")
            statuses: list[RefundStatus] = []
            for request in requests:
                self._require_read(subject, request=request, at=at)
                statuses.append(
                    RefundStatus(
                        request=request,
                        decisions=unit.refunds.list_decisions(
                            request.refund_request_id
                        ),
                        authorizations=unit.refunds.list_authorizations(
                            request.refund_request_id
                        ),
                        evidence=unit.refunds.list_evidence(request.refund_request_id),
                    )
                )
            return RefundRideHistory(ride_id=ride_id, statuses=tuple(statuses))

    def _require_permission(
        self, subject: AuthorizationSubject, permission: str, *, at: datetime
    ) -> None:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, permission, at=at
            ):
                raise RefundConflict("access_denied")

    def _require_read(
        self,
        subject: AuthorizationSubject,
        *,
        request: RefundRequest,
        at: datetime,
    ) -> None:
        if (
            subject.identity_type is IdentityType.RIDER
            and subject.identity_id == request.requested_by_identity_id
        ):
            with self._composition.unit_of_work() as unit:
                if unit.authorization.has_permission(
                    subject.identity_id, TRACE_READ_PERMISSION, at=at
                ) or unit.authorization.has_permission(
                    subject.identity_id, CUSTOMER_CREATE_PERMISSION, at=at
                ):
                    return
        with self._composition.unit_of_work() as unit:
            if unit.authorization.has_permission(
                subject.identity_id, SUPPORT_READ_PERMISSION, at=at
            ) or unit.authorization.has_permission(
                subject.identity_id, TRACE_READ_PERMISSION, at=at
            ):
                return
        raise RefundConflict("refund_status_not_found")

    @staticmethod
    def _validate_idempotency_key(value: str) -> None:
        if not 16 <= len(value) <= 128:
            raise RefundConflict("idempotency_key_invalid")

    @staticmethod
    def _validate_request_amount(
        *,
        refund_type: RefundType,
        amount_minor: int,
        payment_amount_minor: int,
    ) -> None:
        if amount_minor < 0:
            raise RefundConflict("refund_amount_invalid")
        if amount_minor > payment_amount_minor:
            raise RefundConflict("refund_amount_exceeds_payment")
        if (
            refund_type is RefundType.FULL_REFUND
            and amount_minor != payment_amount_minor
        ):
            raise RefundConflict("refund_amount_must_equal_payment")
        if refund_type is RefundType.PARTIAL_REFUND and (
            amount_minor <= 0 or amount_minor >= payment_amount_minor
        ):
            raise RefundConflict("refund_partial_amount_invalid")
