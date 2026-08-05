from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.field_operations.application import FieldOperationsApplication
from BACKEND.field_operations.engine import (
    FieldOperationsConflict,
    case_target,
    review_target,
)
from BACKEND.field_operations.models import (
    AssistanceCase,
    CaseAction,
    CaseStatus,
    FieldPartner,
    PartnerStatus,
    ReviewChecklist,
    ReviewDecision,
    VerificationStatus,
)
from BACKEND.identity.models import IdentityType

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


class _Authorization:
    def has_permission(self, *_args, **_kwargs) -> bool:
        return True


class _Repository:
    def __init__(self, case: AssistanceCase, partner: FieldPartner) -> None:
        self.case = case
        self.partner = partner
        self.transition_called = False

    def get_case(self, _case_id, *, lock=False):
        return self.case

    def get_partner(self, _partner_id):
        return self.partner

    def reserve(self, *_args):
        return self.case.case_id

    def transition_case(self, *_args, **_kwargs):
        self.transition_called = True
        return self.case


class _Unit:
    def __init__(self, repository: _Repository) -> None:
        self.field_operations = repository
        self.authorization = _Authorization()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _Composition:
    def __init__(self, repository: _Repository) -> None:
        self.repository = repository

    def unit_of_work(self):
        return _Unit(self.repository)


def _subject(identity_id):
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=IdentityType.STAFF,
        actor_type=ActorType.STAFF,
    )


def _case(partner_id, status=CaseStatus.SUBMITTED_FOR_REVIEW, version=5):
    return AssistanceCase(
        case_id=uuid4(),
        partner_id=partner_id,
        territory_id=uuid4(),
        subject_type="merchant",
        subject_id=uuid4(),
        owner_identity_id=uuid4(),
        capability_code="merchant.onboarding",
        status=status,
        version=version,
        created_at=NOW,
        updated_at=NOW,
    )


def _partner(identity_id):
    return FieldPartner(
        public_partner_id="AYO-FP-QUALITY1",
        identity_id=identity_id,
        photo_reference="opaque-photo-reference",
        qr_reference_hash="a" * 64,
        verification_status=VerificationStatus.VERIFIED,
        status=PartnerStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def checklist(**changes: bool) -> ReviewChecklist:
    values = {
        "correct_business": True,
        "correct_owner": True,
        "required_verification_completed": True,
        "required_documents_completed": True,
        "no_duplicate_onboarding": True,
        "no_representative_misconduct": True,
        "business_readiness_evidence": True,
    }
    values.update(changes)
    return ReviewChecklist(**values)


def test_canonical_lifecycle_and_correction_loop_are_explicit() -> None:
    assert case_target(CaseStatus.ASSIGNED, CaseAction.START) is CaseStatus.IN_PROGRESS
    assert (
        case_target(CaseStatus.IN_PROGRESS, CaseAction.RECORD_OWNER_ASSISTED)
        is CaseStatus.BUSINESS_OWNER_ASSISTED
    )
    assert (
        case_target(
            CaseStatus.BUSINESS_OWNER_ASSISTED, CaseAction.CONFIRM_OWNER_VERIFICATION
        )
        is CaseStatus.OWNER_VERIFICATION_COMPLETED
    )
    assert (
        case_target(
            CaseStatus.OWNER_VERIFICATION_COMPLETED, CaseAction.SUBMIT_FOR_REVIEW
        )
        is CaseStatus.SUBMITTED_FOR_REVIEW
    )
    assert (
        case_target(CaseStatus.RETURNED_FOR_CORRECTION, CaseAction.RESUME_CORRECTION)
        is CaseStatus.IN_PROGRESS
    )


def test_invalid_terminal_and_replayed_transitions_fail_closed() -> None:
    for state in (
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.SUBMITTED_FOR_REVIEW,
    ):
        with pytest.raises(
            FieldOperationsConflict, match="field_case_transition_invalid"
        ):
            case_target(state, CaseAction.START)


def test_approval_requires_complete_independent_checklist() -> None:
    assert (
        review_target(
            CaseStatus.SUBMITTED_FOR_REVIEW, ReviewDecision.APPROVE, checklist()
        )
        is CaseStatus.APPROVED
    )
    with pytest.raises(
        FieldOperationsConflict, match="field_review_checklist_incomplete"
    ):
        review_target(
            CaseStatus.SUBMITTED_FOR_REVIEW,
            ReviewDecision.APPROVE,
            checklist(correct_owner=False),
        )
    assert (
        review_target(
            CaseStatus.SUBMITTED_FOR_REVIEW,
            ReviewDecision.RETURN,
            checklist(correct_owner=False),
        )
        is CaseStatus.RETURNED_FOR_CORRECTION
    )


def test_review_is_only_available_from_submitted_state() -> None:
    with pytest.raises(FieldOperationsConflict, match="field_case_not_reviewable"):
        review_target(CaseStatus.IN_PROGRESS, ReviewDecision.REJECT, checklist())


def test_representative_cannot_review_own_case() -> None:
    identity_id = uuid4()
    partner = _partner(identity_id)
    repository = _Repository(_case(partner.partner_id), partner)
    with pytest.raises(
        FieldOperationsConflict, match="field_review_self_approval_prohibited"
    ):
        FieldOperationsApplication(_Composition(repository)).review_case(
            _subject(identity_id),
            case_id=repository.case.case_id,
            expected_version=5,
            decision=ReviewDecision.APPROVE,
            checklist=checklist(),
            evidence_reference="independent-review-evidence",
            reason_code=None,
            idempotency_key="quality-review-key-0001",
            at=NOW,
        )
    assert not repository.transition_called


def test_replayed_approved_review_returns_canonical_state_without_duplicate_evidence() -> (
    None
):
    reviewer_id = uuid4()
    partner = _partner(uuid4())
    repository = _Repository(_case(partner.partner_id, CaseStatus.APPROVED, 6), partner)
    result = FieldOperationsApplication(_Composition(repository)).review_case(
        _subject(reviewer_id),
        case_id=repository.case.case_id,
        expected_version=5,
        decision=ReviewDecision.APPROVE,
        checklist=checklist(),
        evidence_reference="independent-review-evidence",
        reason_code=None,
        idempotency_key="quality-review-key-0002",
        at=NOW,
    )
    assert result.status is CaseStatus.APPROVED
    assert not repository.transition_called


def test_security_and_immutable_evidence_guards_are_present() -> None:
    root = Path(__file__).parents[1]
    app = (root / "BACKEND" / "field_operations" / "application.py").read_text(
        encoding="utf-8"
    )
    repository = (
        root / "BACKEND" / "persistence" / "field_operations_repository.py"
    ).read_text(encoding="utf-8")
    migration = (
        root
        / "database"
        / "migrations"
        / "versions"
        / "20260721_0042_field_assistance_quality_lifecycle.py"
    ).read_text(encoding="utf-8")
    assert "field_review_self_approval_prohibited" in app
    assert "field_assignment_not_active" in app
    assert "duplicate_onboarding_claim" in app
    assert "with_for_update" in repository
    assert "field_case_evidence" in repository
    assert "uq_field_case_evidence_version" in migration
    assert "uq_field_case_subject_capability" in migration
    upgrade = migration.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert "DELETE FROM ayo.field_case_evidence" not in upgrade


def test_phase_two_contains_no_financial_or_incentive_authority() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[1] / "BACKEND" / "field_operations").glob(
            "*.py"
        )
    ).lower()
    assert "partner_wallet" not in source
    assert "payroll" not in source
    assert "incentive_amount" not in source
    assert "tax_withholding" not in source
