from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from BACKEND.driver_trust.models import (
    AuthorizationStatus,
    DocumentEvidence,
    DriverVehicleAuthorization,
    EligibilityDecision,
    EligibilityPolicy,
    EligibilityStatus,
    EvidenceStatus,
    EvidenceType,
    OnboardingCase,
    OnboardingState,
    Vehicle,
    VehicleApprovalStatus,
)

TRANSITIONS: dict[OnboardingState, frozenset[OnboardingState]] = {
    OnboardingState.DRAFT: frozenset({OnboardingState.CONTACT_VERIFICATION_PENDING}),
    OnboardingState.CONTACT_VERIFICATION_PENDING: frozenset(
        {OnboardingState.IDENTITY_EVIDENCE_PENDING}
    ),
    OnboardingState.IDENTITY_EVIDENCE_PENDING: frozenset(
        {OnboardingState.DOCUMENT_REVIEW_PENDING}
    ),
    OnboardingState.DOCUMENT_REVIEW_PENDING: frozenset(
        {OnboardingState.VEHICLE_EVIDENCE_PENDING, OnboardingState.REJECTED}
    ),
    OnboardingState.VEHICLE_EVIDENCE_PENDING: frozenset(
        {OnboardingState.OPERATIONS_REVIEW_PENDING}
    ),
    OnboardingState.OPERATIONS_REVIEW_PENDING: frozenset(
        {OnboardingState.APPROVED, OnboardingState.REJECTED}
    ),
    OnboardingState.APPROVED: frozenset(
        {
            OnboardingState.EXPIRED,
            OnboardingState.SUSPENDED,
            OnboardingState.REVERIFICATION_REQUIRED,
        }
    ),
    OnboardingState.REJECTED: frozenset({OnboardingState.APPEAL_PENDING}),
    OnboardingState.EXPIRED: frozenset({OnboardingState.REVERIFICATION_REQUIRED}),
    OnboardingState.SUSPENDED: frozenset(
        {OnboardingState.REVERIFICATION_REQUIRED, OnboardingState.APPEAL_PENDING}
    ),
    OnboardingState.REVERIFICATION_REQUIRED: frozenset(
        {OnboardingState.DOCUMENT_REVIEW_PENDING}
    ),
    OnboardingState.APPEAL_PENDING: frozenset(
        {OnboardingState.OPERATIONS_REVIEW_PENDING, OnboardingState.REJECTED}
    ),
}


def transition_case(
    case: OnboardingCase, target: OnboardingState, *, at: datetime
) -> OnboardingCase:
    if target not in TRANSITIONS[case.state]:
        raise ValueError("Invalid onboarding transition")
    return case.model_copy(
        update={"state": target, "updated_at": at, "version": case.version + 1}
    )


def evaluate_eligibility(
    *,
    driver_identity_id: UUID,
    account_active: bool,
    case: OnboardingCase | None,
    vehicle: Vehicle | None,
    authorization: DriverVehicleAuthorization | None,
    evidence: tuple[DocumentEvidence, ...],
    policy: EligibilityPolicy,
    at: datetime,
    unresolved_restriction: bool = False,
) -> EligibilityDecision:
    at = at.astimezone(UTC)
    reasons: list[str] = []
    approved: dict[EvidenceType, DocumentEvidence] = {}
    contradictory: set[EvidenceType] = set()
    for item in evidence:
        if item.status is EvidenceStatus.APPROVED and item.expiry_date >= at.date():
            if item.evidence_type in approved:
                contradictory.add(item.evidence_type)
            approved[item.evidence_type] = item
    required = set(policy.required_evidence)
    if not policy.inspection_required:
        required.discard(EvidenceType.INSPECTION)
    missing = tuple(sorted(required - approved.keys(), key=str))
    if not account_active:
        reasons.append("account_not_active")
    if case is None or case.state is not OnboardingState.APPROVED:
        reasons.append("onboarding_not_approved")
    if vehicle is None or vehicle.approval_status is not VehicleApprovalStatus.APPROVED:
        reasons.append("vehicle_not_approved")
    if (
        authorization is None
        or authorization.status is not AuthorizationStatus.AUTHORIZED
        or authorization.expires_at <= at
        or vehicle is None
        or authorization.vehicle_id != vehicle.vehicle_id
    ):
        reasons.append("vehicle_authorization_invalid")
    if missing:
        reasons.append("required_evidence_missing_or_expired")
    if contradictory:
        reasons.append("contradictory_current_evidence")
    if unresolved_restriction:
        reasons.append("unresolved_restriction")
    expiries = [
        datetime.combine(item.expiry_date, time.max, tzinfo=UTC)
        for item in approved.values()
    ]
    if authorization is not None:
        expiries.append(authorization.expires_at)
    expiry = min(expiries) if expiries else None
    if (
        not reasons
        and expiry is not None
        and expiry <= at + timedelta(days=policy.expiring_soon_days)
    ):
        reasons.append("evidence_expiring_soon")
        status = EligibilityStatus.REVERIFICATION_REQUIRED
    else:
        status = (
            EligibilityStatus.ELIGIBLE if not reasons else EligibilityStatus.INELIGIBLE
        )
    return EligibilityDecision(
        driver_identity_id=driver_identity_id,
        vehicle_id=None if vehicle is None else vehicle.vehicle_id,
        policy_version=policy.policy_version,
        status=status,
        reason_codes=tuple(reasons or ["all_requirements_current"]),
        missing_evidence=missing,
        expires_at=expiry,
        recomputed_at=at,
        audit_reference=uuid4(),
    )
