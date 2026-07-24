import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.field_operations.engine import (
    FieldOperationsConflict,
    assert_assignment_authority,
    case_action_result,
    case_target,
    review_decision_result,
    review_target,
)
from BACKEND.field_operations.models import (
    ActivityKind,
    AssistanceCase,
    CaseAction,
    CaseEvidence,
    CaseQueue,
    CaseStatus,
    ConductEvidence,
    ConductEvidenceKind,
    FieldActivity,
    FieldPartner,
    ManagementQualityDashboard,
    PartnerAssignment,
    PartnerDashboard,
    PartnerRole,
    PartnerStatus,
    ReviewChecklist,
    ReviewDecision,
    Territory,
    VerificationStatus,
)


class FieldOperationsApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def create_partner(
        self,
        subject: AuthorizationSubject,
        *,
        identity_id: UUID,
        photo_reference: str,
        qr_reference: str,
        idempotency_key: str,
        at: datetime,
    ) -> FieldPartner:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.partner.manage", at)
            partner_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "partner.create",
                f"{identity_id}:{photo_reference}:{self._hash(qr_reference)}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_partner(partner_id)
            if existing is not None:
                return existing
            return unit.field_operations.create_partner(
                FieldPartner(
                    partner_id=partner_id,
                    public_partner_id=f"AYO-FP-{partner_id.hex[:12].upper()}",
                    identity_id=identity_id,
                    photo_reference=photo_reference,
                    qr_reference_hash=self._hash(qr_reference),
                    created_at=at,
                    updated_at=at,
                ),
                actor_id=subject.identity_id,
            )

    def create_role(
        self,
        subject: AuthorizationSubject,
        *,
        code: str,
        public_title: str,
        allowed_activities: tuple[ActivityKind, ...],
        idempotency_key: str,
        at: datetime,
    ) -> PartnerRole:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.configuration.manage", at)
            role_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "role.create",
                f"{code}:{public_title}:{','.join(item.value for item in allowed_activities)}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_role(role_id)
            if existing is not None:
                return existing
            return unit.field_operations.create_role(
                PartnerRole(
                    role_id=role_id,
                    code=code,
                    public_title=public_title,
                    allowed_activities=allowed_activities,
                ),
                actor_id=subject.identity_id,
                at=at,
            )

    def update_partner_status(
        self,
        subject: AuthorizationSubject,
        *,
        partner_id: UUID,
        expected_version: int,
        status: PartnerStatus,
        verification_status: VerificationStatus,
        idempotency_key: str,
        at: datetime,
    ) -> FieldPartner:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.partner.manage", at)
            current = unit.field_operations.get_partner(partner_id)
            if current is None:
                raise FieldOperationsConflict("field_partner_not_found")
            unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "partner.status",
                f"{partner_id}:{expected_version}:{status}:{verification_status}",
                partner_id,
                at,
            )
            if current.version != expected_version:
                if (
                    current.status is status
                    and current.verification_status is verification_status
                ):
                    return current
                raise FieldOperationsConflict("field_partner_version_conflict")
            return unit.field_operations.update_partner_status(
                current,
                expected_version=expected_version,
                status=status,
                verification_status=verification_status,
                actor_id=subject.identity_id,
                at=at,
            )

    def create_territory(
        self,
        subject: AuthorizationSubject,
        *,
        market_code: str,
        region: str,
        city: str,
        district: str | None,
        name: str,
        idempotency_key: str,
        at: datetime,
    ) -> Territory:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.configuration.manage", at)
            territory_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "territory.create",
                f"{market_code}:{region}:{city}:{district}:{name}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_territory(territory_id)
            if existing is not None:
                return existing
            return unit.field_operations.create_territory(
                Territory(
                    territory_id=territory_id,
                    market_code=market_code,
                    region=region,
                    city=city,
                    district=district,
                    name=name,
                ),
                actor_id=subject.identity_id,
                at=at,
            )

    def assign_partner(
        self,
        subject: AuthorizationSubject,
        *,
        partner_id: UUID,
        role_id: UUID,
        territory_id: UUID,
        starts_at: datetime,
        ends_at: datetime | None,
        idempotency_key: str,
        at: datetime,
    ) -> PartnerAssignment:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.assignment.manage", at)
            partner = unit.field_operations.get_partner(partner_id)
            role = unit.field_operations.get_role(role_id)
            territory = unit.field_operations.get_territory(territory_id)
            if (
                partner is None
                or role is None
                or territory is None
                or not territory.active
            ):
                raise FieldOperationsConflict("field_assignment_reference_invalid")
            assignment_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "assignment.create",
                f"{partner_id}:{role_id}:{territory_id}:{starts_at}:{ends_at}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_assignment(assignment_id)
            if existing is not None:
                return existing
            return unit.field_operations.create_assignment(
                PartnerAssignment(
                    assignment_id=assignment_id,
                    partner_id=partner_id,
                    role_id=role_id,
                    territory_id=territory_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                ),
                actor_id=subject.identity_id,
                at=at,
            )

    def create_case(
        self,
        subject: AuthorizationSubject,
        *,
        assignment_id: UUID,
        subject_type: str,
        subject_id: UUID,
        owner_identity_id: UUID | None = None,
        capability_code: str,
        idempotency_key: str,
        at: datetime,
    ) -> AssistanceCase:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.case.manage", at)
            partner = unit.field_operations.partner_for_identity(subject.identity_id)
            assignment = unit.field_operations.get_assignment(assignment_id)
            if (
                partner is None
                or assignment is None
                or assignment.partner_id != partner.partner_id
            ):
                raise FieldOperationsConflict("field_assignment_not_active")
            case_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "case.create",
                f"{assignment_id}:{subject_type}:{subject_id}:{capability_code}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_case(case_id)
            if existing is not None:
                return existing
            duplicate = unit.field_operations.find_case_by_subject(
                subject_type, subject_id, capability_code
            )
            if duplicate is not None:
                raise FieldOperationsConflict("duplicate_onboarding_claim")
            return unit.field_operations.create_case(
                AssistanceCase(
                    case_id=case_id,
                    partner_id=partner.partner_id,
                    territory_id=assignment.territory_id,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    owner_identity_id=owner_identity_id,
                    capability_code=capability_code,
                    created_at=at,
                    updated_at=at,
                ),
                actor_id=subject.identity_id,
            )

    def transition_case(
        self,
        subject: AuthorizationSubject,
        *,
        case_id: UUID,
        expected_version: int,
        action: CaseAction,
        evidence_reference: str,
        idempotency_key: str,
        at: datetime,
    ) -> AssistanceCase:
        with self._composition.unit_of_work() as unit:
            permission = (
                "field_operations.case.confirm_owner"
                if action is CaseAction.CONFIRM_OWNER_VERIFICATION
                else "field_operations.case.manage"
            )
            self._permission(unit, subject, permission, at)
            current = unit.field_operations.get_case(case_id, lock=True)
            if current is None:
                raise FieldOperationsConflict("field_case_not_found")
            replay_target = case_action_result(action)
            actor_role = (
                "owner"
                if action is CaseAction.CONFIRM_OWNER_VERIFICATION
                else "representative"
            )
            if actor_role == "owner":
                if current.owner_identity_id != subject.identity_id:
                    raise FieldOperationsConflict("field_case_owner_required")
            else:
                self._assert_case_representative(unit, subject, current, at)
            unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "case.transition",
                f"{case_id}:{expected_version}:{action}:{evidence_reference}",
                case_id,
                at,
            )
            if current.version != expected_version:
                if current.status is replay_target:
                    return current
                raise FieldOperationsConflict("field_case_version_conflict")
            target = case_target(current.status, action)
            return unit.field_operations.transition_case(
                current,
                target=target,
                actor_id=subject.identity_id,
                actor_role=actor_role,
                evidence_reference=evidence_reference,
                expected_version=expected_version,
                at=at,
            )

    def review_case(
        self,
        subject: AuthorizationSubject,
        *,
        case_id: UUID,
        expected_version: int,
        decision: ReviewDecision,
        checklist: ReviewChecklist,
        evidence_reference: str,
        reason_code: str | None,
        idempotency_key: str,
        at: datetime,
    ) -> AssistanceCase:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.case.review", at)
            current = unit.field_operations.get_case(case_id, lock=True)
            if current is None:
                raise FieldOperationsConflict("field_case_not_found")
            partner = unit.field_operations.get_partner(current.partner_id)
            if partner is None:
                raise FieldOperationsConflict("field_partner_not_found")
            if partner.identity_id == subject.identity_id:
                raise FieldOperationsConflict("field_review_self_approval_prohibited")
            if (
                decision in {ReviewDecision.RETURN, ReviewDecision.REJECT}
                and not reason_code
            ):
                raise FieldOperationsConflict("field_review_reason_required")
            if decision is ReviewDecision.APPROVE and not checklist.complete():
                raise FieldOperationsConflict("field_review_checklist_incomplete")
            replay_target = review_decision_result(decision)
            unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "case.review",
                f"{case_id}:{expected_version}:{decision}:{checklist.model_dump_json()}:{evidence_reference}:{reason_code}",
                case_id,
                at,
            )
            if current.version != expected_version:
                if current.status is replay_target:
                    return current
                raise FieldOperationsConflict("field_case_version_conflict")
            target = review_target(current.status, decision, checklist)
            return unit.field_operations.transition_case(
                current,
                target=target,
                actor_id=subject.identity_id,
                actor_role="reviewer",
                evidence_reference=evidence_reference,
                reason_code=reason_code,
                checklist=checklist,
                expected_version=expected_version,
                at=at,
            )

    def record_conduct_evidence(
        self,
        subject: AuthorizationSubject,
        *,
        partner_id: UUID,
        kind: ConductEvidenceKind,
        evidence_reference: str,
        idempotency_key: str,
        at: datetime,
    ) -> ConductEvidence:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.quality.record", at)
            evidence_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "conduct.record",
                f"{partner_id}:{kind}:{evidence_reference}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_conduct_evidence(evidence_id)
            if existing is not None:
                return existing
            return unit.field_operations.append_conduct_evidence(
                ConductEvidence(
                    evidence_id=evidence_id,
                    partner_id=partner_id,
                    kind=kind,
                    evidence_reference=evidence_reference,
                    recorded_by_identity_id=subject.identity_id,
                    occurred_at=at,
                )
            )

    def representative_cases(
        self,
        subject: AuthorizationSubject,
        *,
        statuses: tuple[CaseStatus, ...],
        cursor: UUID | None,
        limit: int,
        at: datetime,
    ) -> CaseQueue:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.dashboard.read_own", at)
            partner = unit.field_operations.partner_for_identity(subject.identity_id)
            if partner is None:
                raise FieldOperationsConflict("field_partner_not_found")
            return unit.field_operations.case_queue(
                partner_id=partner.partner_id,
                statuses=statuses,
                cursor=cursor,
                limit=limit,
            )

    def review_queue(
        self,
        subject: AuthorizationSubject,
        *,
        cursor: UUID | None,
        limit: int,
        at: datetime,
    ) -> CaseQueue:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.case.review", at)
            return unit.field_operations.case_queue(
                partner_id=None,
                statuses=(CaseStatus.SUBMITTED_FOR_REVIEW,),
                cursor=cursor,
                limit=limit,
            )

    def review_evidence(
        self,
        subject: AuthorizationSubject,
        *,
        case_id: UUID,
        at: datetime,
    ) -> tuple[CaseEvidence, ...]:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.case.review", at)
            if unit.field_operations.get_case(case_id) is None:
                raise FieldOperationsConflict("field_case_not_found")
            return unit.field_operations.case_evidence(case_id)

    def management_quality_dashboard(
        self, subject: AuthorizationSubject, *, territory_id: UUID | None, at: datetime
    ) -> ManagementQualityDashboard:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.quality.read", at)
            return unit.field_operations.quality_dashboard(territory_id)

    def record_activity(
        self,
        subject: AuthorizationSubject,
        *,
        assignment_id: UUID,
        case_id: UUID | None,
        kind: ActivityKind,
        subject_type: str,
        subject_id: UUID,
        evidence_reference: str,
        quality_status: str | None,
        idempotency_key: str,
        at: datetime,
    ) -> FieldActivity:
        with self._composition.unit_of_work() as unit:
            self._permission(unit, subject, "field_operations.activity.record", at)
            partner = unit.field_operations.partner_for_identity(subject.identity_id)
            if partner is None:
                raise FieldOperationsConflict("field_partner_not_found")
            assignment = unit.field_operations.get_assignment(assignment_id)
            if assignment is None or assignment.partner_id != partner.partner_id:
                raise FieldOperationsConflict("field_assignment_not_active")
            role = unit.field_operations.get_role(assignment.role_id)
            assert_assignment_authority(partner, assignment, role, activity=kind, at=at)
            activity_id = unit.field_operations.reserve(
                subject.identity_id,
                idempotency_key,
                "activity.record",
                f"{assignment_id}:{case_id}:{kind}:{subject_type}:{subject_id}:{evidence_reference}:{quality_status}",
                uuid4(),
                at,
            )
            existing = unit.field_operations.get_activity(activity_id)
            if existing is not None:
                return existing
            return unit.field_operations.append_activity(
                FieldActivity(
                    activity_id=activity_id,
                    partner_id=partner.partner_id,
                    assignment_id=assignment_id,
                    case_id=case_id,
                    territory_id=assignment.territory_id,
                    kind=kind,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    evidence_reference=evidence_reference,
                    quality_status=quality_status,
                    occurred_at=at,
                ),
                actor_id=subject.identity_id,
            )

    def dashboard(
        self, subject: AuthorizationSubject, *, day_start: datetime, day_end: datetime
    ) -> PartnerDashboard:
        if day_end <= day_start or (day_end - day_start).days > 2:
            raise FieldOperationsConflict("dashboard_window_invalid")
        with self._composition.unit_of_work() as unit:
            self._permission(
                unit, subject, "field_operations.dashboard.read_own", day_end
            )
            partner = unit.field_operations.partner_for_identity(subject.identity_id)
            if partner is None:
                raise FieldOperationsConflict("field_partner_not_found")
            assignments = unit.field_operations.active_assignments(
                partner.partner_id, day_end
            )
            counts = unit.field_operations.dashboard_counts(
                partner.partner_id, day_start, day_end
            )
            case_counts = unit.field_operations.representative_status_counts(
                partner.partner_id
            )
            return PartnerDashboard(
                partner=partner,
                assignments=assignments,
                today_activities=counts[0],
                completed_onboardings=counts[1],
                pending_work=counts[2],
                active_cases=sum(
                    case_counts.get(state.value, 0)
                    for state in (
                        CaseStatus.ASSIGNED,
                        CaseStatus.IN_PROGRESS,
                        CaseStatus.BUSINESS_OWNER_ASSISTED,
                        CaseStatus.OWNER_VERIFICATION_COMPLETED,
                    )
                ),
                pending_review=case_counts.get(
                    CaseStatus.SUBMITTED_FOR_REVIEW.value, 0
                ),
                approved_cases=case_counts.get(CaseStatus.APPROVED.value, 0),
                returned_cases=case_counts.get(
                    CaseStatus.RETURNED_FOR_CORRECTION.value, 0
                ),
                rejected_cases=case_counts.get(CaseStatus.REJECTED.value, 0),
            )

    def verify_public_qr(self, *, qr_reference: str) -> dict[str, str | bool]:
        with self._composition.unit_of_work() as unit:
            partner = unit.field_operations.partner_by_qr_hash(self._hash(qr_reference))
            if partner is None:
                raise FieldOperationsConflict("field_partner_not_found")
            return {
                "partner_id": partner.public_partner_id,
                "verified": partner.verification_status is VerificationStatus.VERIFIED,
                "active": partner.status is PartnerStatus.ACTIVE,
            }

    @staticmethod
    def _assert_case_representative(
        unit: Any,
        subject: AuthorizationSubject,
        case: AssistanceCase,
        at: datetime,
    ) -> None:
        partner = unit.field_operations.partner_for_identity(subject.identity_id)
        if partner is None or partner.partner_id != case.partner_id:
            raise FieldOperationsConflict("field_case_representative_required")
        assignments = unit.field_operations.active_assignments(partner.partner_id, at)
        if (
            partner.status is not PartnerStatus.ACTIVE
            or partner.verification_status is not VerificationStatus.VERIFIED
            or not any(item.territory_id == case.territory_id for item in assignments)
        ):
            raise FieldOperationsConflict("field_assignment_not_active")

    @staticmethod
    def _permission(
        unit: Any, subject: AuthorizationSubject, code: str, at: datetime
    ) -> None:
        if not unit.authorization.has_permission(subject.identity_id, code, at=at):
            raise FieldOperationsConflict("access_denied")

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
