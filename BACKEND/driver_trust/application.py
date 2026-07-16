from datetime import datetime
from uuid import UUID

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.driver_trust.engine import transition_case
from BACKEND.driver_trust.models import (
    DocumentEvidence,
    EvidenceStatus,
    OnboardingCase,
    OnboardingState,
)
from BACKEND.persistence.composition import PostgresRepositoryComposition


class DriverTrustAccessDenied(RuntimeError):
    """Privacy-safe denial; callers must not infer another driver's records."""


class DriverTrustApplication:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def get_own_case(
        self, *, subject: AuthorizationSubject, case_id: UUID
    ) -> OnboardingCase:
        with self._composition.unit_of_work() as unit:
            case = unit.driver_trust.get_case(case_id)
            if case is None or case.driver_identity_id != subject.identity_id:
                raise DriverTrustAccessDenied("resource_access_denied")
            return case

    def review_transition(
        self,
        *,
        subject: AuthorizationSubject,
        case_id: UUID,
        target: OnboardingState,
        reason_code: str,
        at: datetime,
    ) -> OnboardingCase:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "driver_trust.review", at=at
            ):
                raise DriverTrustAccessDenied("access_denied")
            case = unit.driver_trust.get_case(case_id)
            if case is None:
                raise DriverTrustAccessDenied("resource_access_denied")
            changed = transition_case(case, target, at=at)
            saved = unit.driver_trust.save_case(changed, expected_version=case.version)
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(subject.identity_id),
                    session_id=subject.session_id,
                    action="driver_trust.onboarding.transition",
                    resource_type="driver_onboarding_case",
                    resource_id=str(case_id),
                    outcome=AuditOutcome.SUCCESS,
                    reason=reason_code,
                    correlation_id=saved.case_id,
                    source_module="driver_trust",
                    safe_metadata={
                        "from": case.state.value,
                        "to": target.value,
                        "policy_version": case.policy_version,
                    },
                )
            )
            return saved

    def review_evidence(
        self,
        *,
        subject: AuthorizationSubject,
        evidence_id: UUID,
        outcome: EvidenceStatus,
        expected_version: int,
        reason_codes: tuple[str, ...],
        at: datetime,
    ) -> DocumentEvidence:
        """Reviewer identity is always the verified subject, never request data."""
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "driver_trust.review", at=at
            ):
                raise DriverTrustAccessDenied("access_denied")
            reviewed = unit.driver_trust.review_evidence(
                evidence_id,
                status=outcome,
                reviewer_identity_id=subject.identity_id,
                reason_codes=reason_codes,
                reviewed_at=at,
                expected_version=expected_version,
            )
            unit.audit_events.append(
                AuditEvent(
                    actor_type=subject.actor_type,
                    actor_id=str(subject.identity_id),
                    session_id=subject.session_id,
                    action="driver_trust.evidence.review",
                    resource_type="driver_document_evidence",
                    resource_id=str(evidence_id),
                    outcome=AuditOutcome.SUCCESS,
                    reason=reason_codes[0] if reason_codes else "review_completed",
                    correlation_id=evidence_id,
                    source_module="driver_trust",
                    safe_metadata={
                        "outcome": outcome.value,
                        "policy_version": reviewed.policy_version,
                    },
                )
            )
            return reviewed
