from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from BACKEND.driver_trust.engine import evaluate_eligibility, transition_case
from BACKEND.driver_trust.models import (
    AuthorizationStatus,
    DocumentEvidence,
    DriverVehicleAuthorization,
    EligibilityPolicy,
    EligibilityStatus,
    EvidenceStatus,
    EvidenceType,
    OnboardingCase,
    OnboardingState,
    Vehicle,
    VehicleApprovalStatus,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def case(state: OnboardingState = OnboardingState.DRAFT) -> OnboardingCase:
    return OnboardingCase(
        driver_identity_id=uuid4(),
        state=state,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )


def evidence(
    driver_id, kind: EvidenceType, *, expiry_days: int = 365
) -> DocumentEvidence:
    return DocumentEvidence(
        case_id=uuid4(),
        driver_identity_id=driver_id,
        evidence_type=kind,
        immutable_reference=f"vault://metadata/{uuid4()}",
        issuing_authority_code="ethiopia.authority.pending",
        document_reference_hash=uuid4().bytes + uuid4().bytes,
        issue_date=date(2025, 1, 1),
        expiry_date=(NOW + timedelta(days=expiry_days)).date(),
        status=EvidenceStatus.APPROVED,
        policy_version="identity.v1",
        reviewer_identity_id=uuid4(),
        submitted_at=NOW,
        reviewed_at=NOW,
    )


def test_onboarding_transitions_are_typed_and_reject_shortcuts() -> None:
    draft = case()
    pending = transition_case(
        draft, OnboardingState.CONTACT_VERIFICATION_PENDING, at=NOW
    )
    assert pending.version == 2
    with pytest.raises(ValueError, match="Invalid onboarding transition"):
        transition_case(draft, OnboardingState.APPROVED, at=NOW)


def test_evidence_requires_dates_and_human_review_metadata() -> None:
    with pytest.raises(ValueError, match="Evidence expiry"):
        evidence(uuid4(), EvidenceType.LEGAL_IDENTITY).model_copy(
            update={"expiry_date": date(2024, 1, 1)}
        ).__class__.model_validate(
            evidence(uuid4(), EvidenceType.LEGAL_IDENTITY).model_dump()
            | {"expiry_date": date(2024, 1, 1)}
        )
    item = evidence(uuid4(), EvidenceType.DRIVER_LICENCE)
    with pytest.raises(ValueError, match="reviewer"):
        DocumentEvidence.model_validate(
            item.model_dump() | {"reviewer_identity_id": None}
        )


def test_eligibility_fails_closed_and_never_uses_scores() -> None:
    driver = uuid4()
    policy = EligibilityPolicy(
        policy_version="identity.v1", required_evidence=frozenset(EvidenceType)
    )
    decision = evaluate_eligibility(
        driver_identity_id=driver,
        account_active=True,
        case=None,
        vehicle=None,
        authorization=None,
        evidence=(),
        policy=policy,
        at=NOW,
    )
    assert decision.status is EligibilityStatus.INELIGIBLE
    assert set(decision.missing_evidence) == set(EvidenceType)
    assert "onboarding_not_approved" in decision.reason_codes


def test_current_human_approved_evidence_produces_bounded_eligibility() -> None:
    driver = uuid4()
    approved_case = case(OnboardingState.APPROVED).model_copy(
        update={"driver_identity_id": driver}
    )
    vehicle = Vehicle(
        canonical_reference_hash=uuid4().bytes + uuid4().bytes,
        category="vehicle.standard",
        approval_status=VehicleApprovalStatus.APPROVED,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )
    authorization = DriverVehicleAuthorization(
        driver_identity_id=driver,
        vehicle_id=vehicle.vehicle_id,
        status=AuthorizationStatus.AUTHORIZED,
        policy_version="identity.v1",
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=400),
    )
    items = tuple(evidence(driver, kind) for kind in EvidenceType)
    policy = EligibilityPolicy(
        policy_version="identity.v1", required_evidence=frozenset(EvidenceType)
    )
    decision = evaluate_eligibility(
        driver_identity_id=driver,
        account_active=True,
        case=approved_case,
        vehicle=vehicle,
        authorization=authorization,
        evidence=items,
        policy=policy,
        at=NOW,
    )
    assert decision.status is EligibilityStatus.ELIGIBLE
    assert decision.reason_codes == ("all_requirements_current",)
    assert decision.expires_at is not None


def test_expiry_restriction_conflict_and_reverification_are_explainable() -> None:
    driver = uuid4()
    item = evidence(driver, EvidenceType.LEGAL_IDENTITY, expiry_days=5)
    policy = EligibilityPolicy(
        policy_version="identity.v2",
        required_evidence=frozenset({EvidenceType.LEGAL_IDENTITY}),
    )
    approved_case = case(OnboardingState.APPROVED).model_copy(
        update={"driver_identity_id": driver}
    )
    vehicle = Vehicle(
        canonical_reference_hash=uuid4().bytes + uuid4().bytes,
        category="vehicle.standard",
        approval_status=VehicleApprovalStatus.APPROVED,
        policy_version="identity.v2",
        created_at=NOW,
        updated_at=NOW,
    )
    authorization = DriverVehicleAuthorization(
        driver_identity_id=driver,
        vehicle_id=vehicle.vehicle_id,
        status=AuthorizationStatus.AUTHORIZED,
        policy_version="identity.v2",
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=100),
    )
    expiring = evaluate_eligibility(
        driver_identity_id=driver,
        account_active=True,
        case=approved_case,
        vehicle=vehicle,
        authorization=authorization,
        evidence=(item,),
        policy=policy,
        at=NOW,
    )
    assert expiring.status is EligibilityStatus.REVERIFICATION_REQUIRED
    restricted = evaluate_eligibility(
        driver_identity_id=driver,
        account_active=True,
        case=approved_case,
        vehicle=vehicle,
        authorization=authorization,
        evidence=(item, item.model_copy(update={"evidence_id": uuid4()})),
        policy=policy,
        at=NOW,
        unresolved_restriction=True,
    )
    assert restricted.status is EligibilityStatus.INELIGIBLE
    assert "contradictory_current_evidence" in restricted.reason_codes
    assert "unresolved_restriction" in restricted.reason_codes


def test_vehicle_substitution_fails_closed() -> None:
    driver = uuid4()
    approved_case = case(OnboardingState.APPROVED).model_copy(
        update={"driver_identity_id": driver}
    )
    vehicle = Vehicle(
        canonical_reference_hash=uuid4().bytes + uuid4().bytes,
        category="vehicle.standard",
        approval_status=VehicleApprovalStatus.APPROVED,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )
    authorization = DriverVehicleAuthorization(
        driver_identity_id=driver,
        vehicle_id=uuid4(),
        status=AuthorizationStatus.AUTHORIZED,
        policy_version="identity.v1",
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=100),
    )
    policy = EligibilityPolicy(
        policy_version="identity.v1", required_evidence=frozenset()
    )
    decision = evaluate_eligibility(
        driver_identity_id=driver,
        account_active=True,
        case=approved_case,
        vehicle=vehicle,
        authorization=authorization,
        evidence=(),
        policy=policy,
        at=NOW,
    )
    assert decision.status is EligibilityStatus.INELIGIBLE
    assert "vehicle_authorization_invalid" in decision.reason_codes
