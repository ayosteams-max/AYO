import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.merchant.models import MerchantState
from BACKEND.merchant_orders.engine import MerchantOrderConflict, decision_transition
from BACKEND.merchant_orders.models import (
    MerchantDecisionCase,
    MerchantDecisionEvidence,
    MerchantDecisionPolicy,
    MerchantDecisionState,
    MerchantRejectionReason,
)
from BACKEND.ordering.models import OrderState


class MerchantDecisionApplication:
    def __init__(self, composition: Any, policy: MerchantDecisionPolicy) -> None:
        self._composition = composition
        self._policy = policy

    def admit(
        self,
        subject: AuthorizationSubject,
        *,
        order_id: UUID,
        merchant_location_id: UUID,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantDecisionCase:
        instant = self._at(at)
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant_orders.admit_decision", at=instant
            ):
                raise MerchantOrderConflict("merchant_decision_admission_denied")
            order = unit.merchant_orders.get_order(order_id, lock=True)
            if (
                order is None
                or order.state is not OrderState.WAITING_FOR_MERCHANT_CONFIRMATION
            ):
                raise MerchantOrderConflict("merchant_decision_order_invalid")
            if not unit.merchant_orders.branch_is_active(
                order.merchant_id, merchant_location_id
            ):
                raise MerchantOrderConflict("merchant_location_invalid")
            value = MerchantDecisionCase(
                order_id=order.order_id,
                order_version=order.version,
                merchant_id=order.merchant_id,
                merchant_location_id=merchant_location_id,
                policy_name=self._policy.name,
                policy_version=self._policy.version,
                window_started_at=instant,
                expires_at=instant
                + timedelta(seconds=self._policy.maximum_window_seconds),
                created_at=instant,
                updated_at=instant,
            )
            result = unit.merchant_orders.admit_decision_case(value)
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(subject.identity_id),
                    session_id=subject.session_id,
                    action="merchant_orders.decision.admit",
                    resource_type="merchant_decision_case",
                    resource_id=str(result.decision_case_id),
                    outcome=AuditOutcome.SUCCESS,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    source_module="merchant_orders",
                    safe_metadata={
                        "operation": "merchant_decision_admit",
                        "policy_version": result.policy_version,
                        "state_to": result.state.value,
                    },
                )
            )
            return result

    def decide(
        self,
        subject: AuthorizationSubject,
        *,
        decision_case_id: UUID,
        expected_version: int,
        result: MerchantDecisionState,
        rejection_reason: MerchantRejectionReason | None,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantDecisionCase:
        if result not in {
            MerchantDecisionState.ACCEPTED,
            MerchantDecisionState.REJECTED,
        }:
            raise MerchantOrderConflict("merchant_decision_result_invalid")
        if (result is MerchantDecisionState.REJECTED) != (rejection_reason is not None):
            raise MerchantOrderConflict("merchant_decision_reason_invalid")
        instant = self._at(at)
        payload = {
            "decision_case_id": str(decision_case_id),
            "expected_version": expected_version,
            "result": result.value,
            "rejection_reason": (
                None if rejection_reason is None else rejection_reason.value
            ),
        }
        with self._composition.unit_of_work() as unit:
            previous, created = unit.merchant_orders.reserve_decision(
                actor_identity_id=subject.identity_id,
                decision_case_id=decision_case_id,
                operation="decide",
                key=idempotency_key,
                payload=payload,
                at=instant,
            )
            if not created:
                existing = unit.merchant_orders.get_decision_case(decision_case_id)
                if existing is None or existing.version != previous:
                    raise MerchantOrderConflict("idempotency_result_unavailable")
                return existing
            case = unit.merchant_orders.get_decision_case(decision_case_id, lock=True)
            if case is None:
                raise MerchantOrderConflict("merchant_decision_not_found")
            if case.version != expected_version:
                raise MerchantOrderConflict("merchant_decision_version_conflict")
            merchant = unit.merchants.get_profile(case.merchant_id, lock=False)
            if merchant is None or merchant.state is not MerchantState.APPROVED:
                raise MerchantOrderConflict("merchant_unavailable")
            authority_basis = "merchant_owner"
            if subject.identity_id != merchant.owner_identity_id:
                authority = unit.merchant_orders.staff_authority(
                    merchant_id=case.merchant_id,
                    location_id=case.merchant_location_id,
                    staff_identity_id=subject.identity_id,
                    at=instant,
                )
                if authority is None:
                    raise MerchantOrderConflict("access_denied")
                authority_basis = authority.authority_basis
            target = decision_transition(case, result, at=instant)
            evidence = self._evidence(
                case,
                owner_identity_id=merchant.owner_identity_id,
                authenticated_subject_id=subject.identity_id,
                authority_basis=authority_basis,
                result=target,
                rejection_reason=rejection_reason,
                correlation_id=correlation_id,
                causation_id=causation_id,
                at=instant,
            )
            updated = unit.merchant_orders.terminal_decision(
                case,
                evidence,
                idempotency_actor_id=subject.identity_id,
                idempotency_key=idempotency_key,
            )
            unit.audit_events.append(
                self._audit(
                    subject.actor_type,
                    subject.identity_id,
                    subject.session_id,
                    updated,
                    evidence,
                    idempotency_key=idempotency_key,
                )
            )
            return updated

    def expire_due(
        self,
        subject: AuthorizationSubject,
        *,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
        limit: int = 100,
    ) -> int:
        instant = self._at(at)
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant_orders.expire_decisions", at=instant
            ):
                raise MerchantOrderConflict("merchant_decision_expiry_denied")
            cases = unit.merchant_orders.due_decision_cases(
                at=instant, limit=min(max(limit, 1), 100)
            )
            for case in cases:
                merchant = unit.merchants.get_profile(case.merchant_id, lock=False)
                if merchant is None:
                    raise MerchantOrderConflict("merchant_unavailable")
                target = decision_transition(
                    case, MerchantDecisionState.EXPIRED, at=instant
                )
                evidence = self._evidence(
                    case,
                    owner_identity_id=merchant.owner_identity_id,
                    authenticated_subject_id=None,
                    authority_basis="system_policy_expiry",
                    result=target,
                    rejection_reason=None,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    at=instant,
                )
                unit.merchant_orders.terminal_decision(
                    case,
                    evidence,
                    idempotency_actor_id=None,
                    idempotency_key=None,
                )
                unit.audit_events.append(
                    self._audit(
                        ActorType.SYSTEM,
                        None,
                        None,
                        case,
                        evidence,
                        idempotency_key=None,
                    )
                )
            return len(cases)

    @staticmethod
    def _at(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("merchant decision timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _evidence(
        case: MerchantDecisionCase,
        *,
        owner_identity_id: UUID,
        authenticated_subject_id: UUID | None,
        authority_basis: str,
        result: MerchantDecisionState,
        rejection_reason: MerchantRejectionReason | None,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> MerchantDecisionEvidence:
        payload = {
            "decision_case_id": str(case.decision_case_id),
            "order_id": str(case.order_id),
            "merchant_id": str(case.merchant_id),
            "merchant_location_id": str(case.merchant_location_id),
            "authenticated_subject_id": (
                None
                if authenticated_subject_id is None
                else str(authenticated_subject_id)
            ),
            "merchant_owner_identity_id": str(owner_identity_id),
            "authority_basis": authority_basis,
            "result": result.value,
            "rejection_reason": (
                None if rejection_reason is None else rejection_reason.value
            ),
            "policy_name": case.policy_name,
            "policy_version": case.policy_version,
            "decided_at": at.isoformat(),
            "expires_at": case.expires_at.isoformat(),
            "correlation_id": str(correlation_id),
            "causation_id": str(causation_id),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return MerchantDecisionEvidence(
            decision_case_id=case.decision_case_id,
            order_id=case.order_id,
            merchant_id=case.merchant_id,
            merchant_location_id=case.merchant_location_id,
            authenticated_subject_id=authenticated_subject_id,
            merchant_owner_identity_id=owner_identity_id,
            authority_basis=authority_basis,
            result=result,
            rejection_reason=rejection_reason,
            policy_name=case.policy_name,
            policy_version=case.policy_version,
            decided_at=at,
            expires_at=case.expires_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            evidence_hash=digest,
        )

    @staticmethod
    def _audit(
        actor_type: ActorType,
        actor_id: UUID | None,
        session_id: UUID | None,
        case: MerchantDecisionCase,
        evidence: MerchantDecisionEvidence,
        *,
        idempotency_key: str | None,
    ) -> AuditEvent:
        return AuditEvent(
            actor_type=actor_type,
            actor_id=None if actor_id is None else str(actor_id),
            session_id=session_id,
            action=f"merchant_orders.decision.{evidence.result.value}",
            resource_type="merchant_decision_case",
            resource_id=str(case.decision_case_id),
            outcome=AuditOutcome.SUCCESS,
            correlation_id=evidence.correlation_id,
            causation_id=evidence.causation_id,
            source_module="merchant_orders",
            safe_metadata={
                "operation": "merchant_decision",
                "policy_version": evidence.policy_version,
                "state_to": evidence.result.value,
            },
            idempotency_key=idempotency_key,
        )


def preproduction_policy(maximum_window_seconds: int = 300) -> MerchantDecisionPolicy:
    return MerchantDecisionPolicy(
        name="AYO_EAT_MERCHANT_DECISION_POLICY_V1",
        version=1,
        maximum_window_seconds=maximum_window_seconds,
    )
