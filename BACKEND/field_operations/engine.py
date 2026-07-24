from datetime import datetime

from BACKEND.field_operations.models import (
    ActivityKind,
    CaseAction,
    CaseStatus,
    FieldPartner,
    PartnerAssignment,
    PartnerRole,
    PartnerStatus,
    ReviewChecklist,
    ReviewDecision,
    VerificationStatus,
)


class FieldOperationsConflict(ValueError):
    pass


def assert_assignment_authority(
    partner: FieldPartner,
    assignment: PartnerAssignment | None,
    role: PartnerRole | None,
    *,
    activity: ActivityKind,
    at: datetime,
) -> None:
    if (
        partner.status is not PartnerStatus.ACTIVE
        or partner.verification_status is not VerificationStatus.VERIFIED
    ):
        raise FieldOperationsConflict("field_partner_not_active")
    if assignment is None or role is None or not role.active:
        raise FieldOperationsConflict("field_assignment_not_active")
    if assignment.starts_at > at or (
        assignment.ends_at is not None and assignment.ends_at <= at
    ):
        raise FieldOperationsConflict("field_assignment_not_active")
    if activity not in role.allowed_activities:
        raise FieldOperationsConflict("field_activity_not_permitted")


_CASE_TRANSITIONS = {
    (CaseStatus.ASSIGNED, CaseAction.START): CaseStatus.IN_PROGRESS,
    (
        CaseStatus.IN_PROGRESS,
        CaseAction.RECORD_OWNER_ASSISTED,
    ): CaseStatus.BUSINESS_OWNER_ASSISTED,
    (
        CaseStatus.BUSINESS_OWNER_ASSISTED,
        CaseAction.CONFIRM_OWNER_VERIFICATION,
    ): CaseStatus.OWNER_VERIFICATION_COMPLETED,
    (
        CaseStatus.OWNER_VERIFICATION_COMPLETED,
        CaseAction.SUBMIT_FOR_REVIEW,
    ): CaseStatus.SUBMITTED_FOR_REVIEW,
    (
        CaseStatus.RETURNED_FOR_CORRECTION,
        CaseAction.RESUME_CORRECTION,
    ): CaseStatus.IN_PROGRESS,
}


def case_target(current: CaseStatus, action: CaseAction) -> CaseStatus:
    try:
        return _CASE_TRANSITIONS[(current, action)]
    except KeyError as error:
        raise FieldOperationsConflict("field_case_transition_invalid") from error


def case_action_result(action: CaseAction) -> CaseStatus:
    for (_, candidate), target in _CASE_TRANSITIONS.items():
        if candidate is action:
            return target
    raise FieldOperationsConflict("field_case_transition_invalid")


def review_decision_result(decision: ReviewDecision) -> CaseStatus:
    return {
        ReviewDecision.APPROVE: CaseStatus.APPROVED,
        ReviewDecision.RETURN: CaseStatus.RETURNED_FOR_CORRECTION,
        ReviewDecision.REJECT: CaseStatus.REJECTED,
    }[decision]


def review_target(
    current: CaseStatus, decision: ReviewDecision, checklist: ReviewChecklist
) -> CaseStatus:
    if current is not CaseStatus.SUBMITTED_FOR_REVIEW:
        raise FieldOperationsConflict("field_case_not_reviewable")
    if decision is ReviewDecision.APPROVE and not checklist.complete():
        raise FieldOperationsConflict("field_review_checklist_incomplete")
    return review_decision_result(decision)
