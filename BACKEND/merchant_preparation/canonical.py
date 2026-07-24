import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.merchant.models import MerchantState
from BACKEND.merchant_orders.models import MerchantDecisionState
from BACKEND.merchant_preparation.engine import PreparationConflict


class CanonicalPreparationState(StrEnum):
    PENDING = "pending_preparation"
    PREPARING = "preparing"
    READY = "ready_for_pickup"
    UNABLE = "unable_to_prepare"


class CanonicalPreparationAction(StrEnum):
    START = "start"
    MARK_READY = "mark_ready"
    DECLARE_UNABLE = "declare_unable"
    CORRECT_READINESS = "correct_readiness"


class PreparationFailureReason(StrEnum):
    ITEM_OR_MODIFIER_UNAVAILABLE = "item_or_modifier_unavailable_after_acceptance"
    CUSTOMER_INSTRUCTION_UNSUPPORTED = "customer_instruction_cannot_be_honored"
    MERCHANT_CAPACITY_FAILURE = "merchant_capacity_failure"
    EQUIPMENT_OR_UTILITY_FAILURE = "equipment_or_utility_failure"
    FOOD_SAFETY_CONSTRAINT = "food_safety_constraint"
    ORDER_EVIDENCE_INVALID = "composition_or_order_evidence_invalid"
    TECHNICAL_OR_OPERATIONAL_ISSUE = "technical_or_operational_issue"
    OTHER_REVIEW_REQUIRED = "other_review_required"


class ReadinessCorrectionReason(StrEnum):
    PREMATURE = "premature_ready_declaration"
    COMPOSITION_RECHECK = "composition_recheck_required"
    FOOD_SAFETY_RECHECK = "food_safety_recheck_required"
    PACKAGING_OR_SEAL = "packaging_or_seal_issue"
    OTHER_REVIEW_REQUIRED = "other_review_required"


class PreparationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(pattern=r"^AYO_EAT_PREPARATION_POLICY_V1$")
    version: int = Field(default=1, ge=1)
    maximum_estimate_seconds: int = Field(ge=60, le=14_400)


class CanonicalPreparationCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    preparation_case_id: UUID = Field(default_factory=uuid4)
    decision_case_id: UUID
    decision_evidence_id: UUID
    order_id: UUID
    order_version: int = Field(ge=1)
    merchant_id: UUID
    merchant_location_id: UUID
    state: CanonicalPreparationState = CanonicalPreparationState.PENDING
    policy_name: str = Field(pattern=r"^AYO_EAT_PREPARATION_POLICY_V1$")
    policy_version: int = Field(ge=1)
    estimated_ready_at: datetime | None = None
    overdue_observed_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "estimated_ready_at", "overdue_observed_at", "created_at", "updated_at"
    )
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("preparation timestamp must be timezone-aware")
        return None if value is None else value.astimezone(UTC)


class CanonicalPreparationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    preparation_case_id: UUID
    case_version: int = Field(ge=1)
    order_id: UUID
    order_version: int = Field(ge=1)
    decision_evidence_id: UUID
    merchant_id: UUID
    merchant_location_id: UUID
    authenticated_subject_id: UUID
    merchant_owner_identity_id: UUID
    authority_basis: str = Field(min_length=3, max_length=128)
    event_type: str = Field(pattern=r"^commerce\.preparation\.[a-z_]{3,40}$")
    from_state: CanonicalPreparationState | None
    to_state: CanonicalPreparationState
    failure_reason: PreparationFailureReason | None = None
    correction_reason: ReadinessCorrectionReason | None = None
    policy_name: str
    policy_version: int = Field(ge=1)
    occurred_at: datetime
    correlation_id: UUID
    causation_id: UUID
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    retention_class: str = "restricted_regulated_commerce_food_safety"

    @field_validator("occurred_at")
    @classmethod
    def evidence_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence timestamp must be timezone-aware")
        return value.astimezone(UTC)


def transition(
    state: CanonicalPreparationState, action: CanonicalPreparationAction
) -> CanonicalPreparationState:
    allowed = {
        (
            CanonicalPreparationState.PENDING,
            CanonicalPreparationAction.START,
        ): CanonicalPreparationState.PREPARING,
        (
            CanonicalPreparationState.PENDING,
            CanonicalPreparationAction.DECLARE_UNABLE,
        ): CanonicalPreparationState.UNABLE,
        (
            CanonicalPreparationState.PREPARING,
            CanonicalPreparationAction.MARK_READY,
        ): CanonicalPreparationState.READY,
        (
            CanonicalPreparationState.PREPARING,
            CanonicalPreparationAction.DECLARE_UNABLE,
        ): CanonicalPreparationState.UNABLE,
        (
            CanonicalPreparationState.READY,
            CanonicalPreparationAction.CORRECT_READINESS,
        ): CanonicalPreparationState.PREPARING,
    }
    try:
        return allowed[(state, action)]
    except KeyError as error:
        raise PreparationConflict("preparation_transition_not_allowed") from error


class CanonicalPreparationApplication:
    def __init__(self, composition: Any, policy: PreparationPolicy) -> None:
        self._composition = composition
        self._policy = policy

    def admit(
        self,
        subject: AuthorizationSubject,
        *,
        decision_case_id: UUID,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> CanonicalPreparationCase:
        instant = self._at(at)
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant_preparation.admit", at=instant
            ):
                raise PreparationConflict("preparation_admission_denied")
            decision = unit.merchant_orders.get_decision_case(decision_case_id)
            evidence = unit.merchant_orders.get_decision_evidence(decision_case_id)
            if (
                decision is None
                or decision.state is not MerchantDecisionState.ACCEPTED
                or evidence is None
                or evidence.result is not MerchantDecisionState.ACCEPTED
            ):
                raise PreparationConflict("accepted_decision_required")
            case = CanonicalPreparationCase(
                decision_case_id=decision.decision_case_id,
                decision_evidence_id=evidence.evidence_id,
                order_id=decision.order_id,
                order_version=decision.order_version,
                merchant_id=decision.merchant_id,
                merchant_location_id=decision.merchant_location_id,
                policy_name=self._policy.name,
                policy_version=self._policy.version,
                created_at=instant,
                updated_at=instant,
            )
            result = unit.preparation_cases.admit(case, correlation_id, causation_id)
            unit.audit_events.append(
                self._audit(subject, result, "admitted", correlation_id, causation_id)
            )
            return result

    def command(
        self,
        subject: AuthorizationSubject,
        *,
        preparation_case_id: UUID,
        expected_version: int,
        action: CanonicalPreparationAction,
        estimate_seconds: int | None,
        failure_reason: PreparationFailureReason | None,
        correction_reason: ReadinessCorrectionReason | None,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> CanonicalPreparationCase:
        instant = self._at(at)
        self._validate_fields(
            action, estimate_seconds, failure_reason, correction_reason
        )
        payload = {
            "case": str(preparation_case_id),
            "version": expected_version,
            "action": action.value,
            "estimate": estimate_seconds,
            "failure": None if failure_reason is None else failure_reason.value,
            "correction": None
            if correction_reason is None
            else correction_reason.value,
        }
        with self._composition.unit_of_work() as unit:
            previous, created = unit.preparation_cases.reserve(
                subject.identity_id,
                preparation_case_id,
                action.value,
                idempotency_key,
                payload,
                instant,
            )
            if not created:
                result = unit.preparation_cases.get(preparation_case_id)
                if result is None or result.version != previous:
                    raise PreparationConflict("idempotency_result_unavailable")
                return result
            case = unit.preparation_cases.get(preparation_case_id, lock=True)
            if case is None:
                raise PreparationConflict("preparation_not_found")
            if case.version != expected_version:
                raise PreparationConflict("preparation_version_conflict")
            merchant = unit.merchants.get_profile(case.merchant_id, lock=False)
            if merchant is None or merchant.state is not MerchantState.APPROVED:
                raise PreparationConflict("merchant_unavailable")
            authority_basis = "merchant_owner"
            if subject.identity_id != merchant.owner_identity_id:
                authority = unit.preparation_cases.staff_authority(
                    case.merchant_id,
                    case.merchant_location_id,
                    subject.identity_id,
                    action.value,
                    instant,
                )
                if authority is None:
                    raise PreparationConflict("access_denied")
                authority_basis = authority
            target = transition(case.state, action)
            estimate_at = (
                instant + timedelta(seconds=estimate_seconds)
                if estimate_seconds is not None
                else case.estimated_ready_at
            )
            evidence = self._evidence(
                case,
                subject.identity_id,
                merchant.owner_identity_id,
                authority_basis,
                action,
                target,
                failure_reason,
                correction_reason,
                correlation_id,
                causation_id,
                instant,
            )
            result = unit.preparation_cases.apply(
                case,
                target,
                evidence,
                estimate_at,
                subject.identity_id,
                action.value,
                idempotency_key,
            )
            unit.audit_events.append(
                self._audit(
                    subject,
                    result,
                    action.value,
                    correlation_id,
                    causation_id,
                    idempotency_key,
                )
            )
            return result

    def observe_overdue(
        self,
        subject: AuthorizationSubject,
        *,
        preparation_case_id: UUID,
        expected_version: int,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> CanonicalPreparationCase:
        instant = self._at(at)
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant_preparation.observe_overdue", at=instant
            ):
                raise PreparationConflict("overdue_observation_denied")
            case = unit.preparation_cases.get(preparation_case_id, lock=True)
            if case is None or case.version != expected_version:
                raise PreparationConflict("preparation_version_conflict")
            if (
                case.state is not CanonicalPreparationState.PREPARING
                or case.estimated_ready_at is None
                or instant < case.estimated_ready_at
            ):
                raise PreparationConflict("preparation_not_overdue")
            return unit.preparation_cases.observe_overdue(
                case, correlation_id, causation_id, instant
            )

    def _validate_fields(
        self,
        action: CanonicalPreparationAction,
        estimate: int | None,
        failure: PreparationFailureReason | None,
        correction: ReadinessCorrectionReason | None,
    ) -> None:
        if (action is CanonicalPreparationAction.START) != (estimate is not None):
            raise PreparationConflict("preparation_estimate_invalid")
        if (
            estimate is not None
            and not 60 <= estimate <= self._policy.maximum_estimate_seconds
        ):
            raise PreparationConflict("preparation_estimate_invalid")
        if (action is CanonicalPreparationAction.DECLARE_UNABLE) != (
            failure is not None
        ):
            raise PreparationConflict("preparation_failure_reason_invalid")
        if (action is CanonicalPreparationAction.CORRECT_READINESS) != (
            correction is not None
        ):
            raise PreparationConflict("preparation_correction_reason_invalid")

    def _evidence(
        self,
        case: CanonicalPreparationCase,
        actor: UUID,
        owner: UUID,
        authority: str,
        action: CanonicalPreparationAction,
        target: CanonicalPreparationState,
        failure: PreparationFailureReason | None,
        correction: ReadinessCorrectionReason | None,
        correlation: UUID,
        causation: UUID,
        at: datetime,
    ) -> CanonicalPreparationEvidence:
        suffix = {
            CanonicalPreparationAction.START: "started",
            CanonicalPreparationAction.MARK_READY: "ready_for_pickup",
            CanonicalPreparationAction.DECLARE_UNABLE: "unable_to_prepare",
            CanonicalPreparationAction.CORRECT_READINESS: "readiness_corrected",
        }[action]
        payload = {
            "case": str(case.preparation_case_id),
            "version": case.version + 1,
            "actor": str(actor),
            "target": target.value,
            "event": suffix,
            "correlation": str(correlation),
            "causation": str(causation),
            "at": at.isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CanonicalPreparationEvidence(
            preparation_case_id=case.preparation_case_id,
            case_version=case.version + 1,
            order_id=case.order_id,
            order_version=case.order_version,
            decision_evidence_id=case.decision_evidence_id,
            merchant_id=case.merchant_id,
            merchant_location_id=case.merchant_location_id,
            authenticated_subject_id=actor,
            merchant_owner_identity_id=owner,
            authority_basis=authority,
            event_type=f"commerce.preparation.{suffix}",
            from_state=case.state,
            to_state=target,
            failure_reason=failure,
            correction_reason=correction,
            policy_name=case.policy_name,
            policy_version=case.policy_version,
            occurred_at=at,
            correlation_id=correlation,
            causation_id=causation,
            evidence_hash=digest,
        )

    @staticmethod
    def _at(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("preparation timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _audit(
        subject: AuthorizationSubject,
        case: CanonicalPreparationCase,
        action: str,
        correlation: UUID,
        causation: UUID,
        idempotency_key: str | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            actor_type=subject.actor_type,
            actor_id=str(subject.identity_id),
            session_id=subject.session_id,
            action=f"merchant_preparation.{action}",
            resource_type="preparation_case",
            resource_id=str(case.preparation_case_id),
            outcome=AuditOutcome.SUCCESS,
            correlation_id=correlation,
            causation_id=causation,
            source_module="merchant_preparation",
            safe_metadata={"operation": action, "state_to": case.state.value},
            idempotency_key=idempotency_key,
        )


def preproduction_preparation_policy(
    maximum_estimate_seconds: int = 14_400,
) -> PreparationPolicy:
    return PreparationPolicy(
        name="AYO_EAT_PREPARATION_POLICY_V1",
        version=1,
        maximum_estimate_seconds=maximum_estimate_seconds,
    )
