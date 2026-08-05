from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.application import MerchantApplication
from BACKEND.merchant.engine import MerchantConflict
from BACKEND.merchant.models import (
    CatalogueItemState,
    CatalogueKind,
    MerchantKind,
    MerchantProfile,
    MerchantState,
    OnboardingSource,
    PartnerProgram,
    VerificationEvidence,
    VerificationKind,
    VerificationState,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class _Context(AbstractContextManager[Any]):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def __enter__(self) -> Any:
        return self.unit

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _Composition:
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def unit_of_work(self) -> _Context:
        return _Context(self.unit)


def _subject(
    *,
    identity_type: IdentityType = IdentityType.RIDER,
) -> AuthorizationSubject:
    actor = {
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.ANONYMOUS: ActorType.ANONYMOUS,
        IdentityType.SERVICE: ActorType.SERVICE,
    }[identity_type]
    return AuthorizationSubject(
        identity_id=uuid4(), identity_type=identity_type, actor_type=actor
    )


def _profile(
    owner_id: Any,
    *,
    state: MerchantState = MerchantState.DRAFT,
    assisted_by: Any = None,
) -> MerchantProfile:
    return MerchantProfile(
        owner_identity_id=owner_id,
        assisted_by_identity_id=assisted_by,
        legal_name="Addis Kitchen PLC",
        display_name="Addis Kitchen",
        kind=MerchantKind.COMPANY,
        onboarding_source=(
            OnboardingSource.SELF
            if assisted_by is None
            else OnboardingSource.REPRESENTATIVE
        ),
        state=state,
        capability_code="ayo.eat",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )


def _unit() -> Any:
    unit = MagicMock()
    unit.authorization.has_permission.return_value = True
    return unit


def test_registration_is_personal_authorized_and_idempotent() -> None:
    unit = _unit()
    app = MerchantApplication(_Composition(unit))
    for identity_type in (IdentityType.ANONYMOUS, IdentityType.SERVICE):
        with pytest.raises(MerchantConflict, match="personal_identity"):
            app.register(
                _subject(identity_type=identity_type),
                legal_name="Addis Kitchen PLC",
                display_name="Addis Kitchen",
                kind=MerchantKind.COMPANY,
                source=OnboardingSource.SELF,
                capability_code="ayo.eat",
                market_code="ET-AA",
                representative_identity_id=None,
                idempotency_key="merchant-register-0001",
                at=NOW,
            )

    owner = _subject()
    with pytest.raises(MerchantConflict, match="idempotency_key_invalid"):
        app.register(
            owner,
            legal_name="Addis Kitchen PLC",
            display_name="Addis Kitchen",
            kind=MerchantKind.COMPANY,
            source=OnboardingSource.SELF,
            capability_code="ayo.eat",
            market_code="ET-AA",
            representative_identity_id=None,
            idempotency_key="short",
            at=NOW,
        )
    unit.authorization.has_permission.return_value = False
    with pytest.raises(MerchantConflict, match="access_denied"):
        app.register(
            owner,
            legal_name="Addis Kitchen PLC",
            display_name="Addis Kitchen",
            kind=MerchantKind.COMPANY,
            source=OnboardingSource.SELF,
            capability_code="ayo.eat",
            market_code="ET-AA",
            representative_identity_id=None,
            idempotency_key="merchant-register-denied",
            at=NOW,
        )

    unit.authorization.has_permission.return_value = True
    merchant_id = uuid4()
    unit.merchants.reserve.return_value = merchant_id
    unit.merchants.get_profile.return_value = None
    unit.merchants.create_profile.side_effect = lambda value: value
    created = app.register(
        owner,
        legal_name="Addis Kitchen PLC",
        display_name="Addis Kitchen",
        kind=MerchantKind.COMPANY,
        source=OnboardingSource.SELF,
        capability_code="ayo.eat",
        market_code="ET-AA",
        representative_identity_id=None,
        idempotency_key="merchant-register-create",
        at=NOW,
    )
    assert created.owner_identity_id == owner.identity_id
    unit.merchants.get_profile.return_value = created
    replay = app.register(
        owner,
        legal_name="Addis Kitchen PLC",
        display_name="Addis Kitchen",
        kind=MerchantKind.COMPANY,
        source=OnboardingSource.SELF,
        capability_code="ayo.eat",
        market_code="ET-AA",
        representative_identity_id=None,
        idempotency_key="merchant-register-create",
        at=NOW,
    )
    assert replay == created


def test_assisted_registration_requires_representative_authority() -> None:
    owner, representative = _subject(), uuid4()
    unit = _unit()
    unit.authorization.has_permission.side_effect = [True, False]
    app = MerchantApplication(_Composition(unit))
    with pytest.raises(MerchantConflict, match="representative_not_authorized"):
        app.register(
            owner,
            legal_name="Addis Kitchen PLC",
            display_name="Addis Kitchen",
            kind=MerchantKind.COMPANY,
            source=OnboardingSource.REPRESENTATIVE,
            capability_code="ayo.eat",
            market_code="ET-AA",
            representative_identity_id=representative,
            idempotency_key="merchant-assisted-denied",
            at=NOW,
        )

    unit.authorization.has_permission.side_effect = None
    unit.authorization.has_permission.return_value = True
    unit.merchants.reserve.return_value = uuid4()
    unit.merchants.get_profile.return_value = None
    unit.merchants.create_profile.side_effect = lambda value: value
    created = app.register(
        owner,
        legal_name="Addis Kitchen PLC",
        display_name="Addis Kitchen",
        kind=MerchantKind.COMPANY,
        source=OnboardingSource.REPRESENTATIVE,
        capability_code="ayo.eat",
        market_code="ET-AA",
        representative_identity_id=representative,
        idempotency_key="merchant-assisted-create",
        at=NOW,
    )
    assert created.assisted_by_identity_id == representative
    unit.merchants.record_assistance.assert_called_once()


def test_owner_scoped_profile_branch_verification_and_catalogue_actions() -> None:
    owner = _subject()
    profile = _profile(owner.identity_id)
    unit = _unit()
    unit.merchants.get_profile.return_value = profile
    unit.merchants.list_owned.return_value = (profile,)
    unit.merchants.create_branch.side_effect = lambda value: value
    unit.merchants.upsert_verification.side_effect = lambda value: value
    unit.merchants.create_item.side_effect = lambda value: value
    app = MerchantApplication(_Composition(unit))

    assert app.list_owned(owner) == (profile,)
    branch = app.add_branch(
        owner,
        merchant_id=profile.merchant_id,
        name="Bole Branch",
        address_label="Bole Atlas",
        operating_hours={"mon": "08:00-20:00"},
        at=NOW,
    )
    assert branch.merchant_id == profile.merchant_id
    evidence = app.submit_verification(
        owner,
        merchant_id=profile.merchant_id,
        kind=VerificationKind.IDENTITY,
        opaque_reference="verification:opaque:0001",
        expires_at=None,
        at=NOW,
    )
    assert evidence.state is VerificationState.SUBMITTED

    unit.merchants.get_branch_merchant.return_value = uuid4()
    with pytest.raises(MerchantConflict, match="branch_not_found"):
        app.add_catalogue_item(
            owner,
            merchant_id=profile.merchant_id,
            branch_id=branch.branch_id,
            kind=CatalogueKind.FOOD,
            name="Vegetable Tibs",
            description=None,
            category_code="main",
            at=NOW,
        )
    unit.merchants.get_branch_merchant.return_value = profile.merchant_id
    item = app.add_catalogue_item(
        owner,
        merchant_id=profile.merchant_id,
        branch_id=branch.branch_id,
        kind=CatalogueKind.FOOD,
        name="Vegetable Tibs",
        description=None,
        category_code="main",
        at=NOW,
    )
    assert item.state is CatalogueItemState.DRAFT


def test_verification_review_fails_closed_and_advances_only_complete_merchant() -> None:
    reviewer = _subject()
    merchant = _profile(uuid4(), assisted_by=uuid4())
    evidence = VerificationEvidence(
        merchant_id=merchant.merchant_id,
        kind=VerificationKind.IDENTITY,
        state=VerificationState.SUBMITTED,
        opaque_reference="verification:opaque:0001",
        submitted_at=NOW,
    )
    unit = _unit()
    app = MerchantApplication(_Composition(unit))
    unit.authorization.has_permission.return_value = False
    with pytest.raises(MerchantConflict, match="access_denied"):
        app.review_verification(
            reviewer,
            evidence_id=evidence.evidence_id,
            approved=True,
            reason_code=None,
            at=NOW,
        )
    unit.authorization.has_permission.return_value = True
    unit.merchants.get_verification.return_value = None
    with pytest.raises(MerchantConflict, match="verification_not_found"):
        app.review_verification(
            reviewer,
            evidence_id=evidence.evidence_id,
            approved=True,
            reason_code=None,
            at=NOW,
        )
    unit.merchants.get_verification.return_value = evidence
    unit.merchants.review_verification.side_effect = lambda value: value
    unit.merchants.get_profile.return_value = merchant
    unit.merchants.verifications.return_value = tuple(
        evidence.model_copy(update={"kind": kind, "state": VerificationState.APPROVED})
        for kind in (
            VerificationKind.IDENTITY,
            VerificationKind.BUSINESS_LICENCE,
            VerificationKind.TAX_REGISTRATION,
            VerificationKind.BANK_OR_PAYMENT,
        )
    )
    reviewed = app.review_verification(
        reviewer,
        evidence_id=evidence.evidence_id,
        approved=True,
        reason_code=None,
        at=NOW,
    )
    assert reviewed.state is VerificationState.APPROVED
    unit.merchants.set_profile_state.assert_called_once()
    unit.merchants.record_assistance.assert_called_once()

    unit.merchants.get_profile.return_value = None
    with pytest.raises(MerchantConflict, match="merchant_not_found"):
        app.review_verification(
            reviewer,
            evidence_id=evidence.evidence_id,
            approved=False,
            reason_code="invalid",
            at=NOW,
        )


def test_management_program_readiness_and_dashboard_boundaries() -> None:
    owner = _subject()
    merchant = _profile(owner.identity_id, state=MerchantState.APPROVED)
    unit = _unit()
    unit.merchants.get_profile.return_value = merchant
    app = MerchantApplication(_Composition(unit))
    program = PartnerProgram(
        code="founding.merchant",
        badge_label="Founding Merchant",
        capability_code="ayo.eat",
        market_code="ET-AA",
        opens_at=NOW - timedelta(days=1),
        closes_at=NOW + timedelta(days=1),
    )

    unit.authorization.has_permission.return_value = False
    with pytest.raises(MerchantConflict, match="access_denied"):
        app.configure_program(owner, program=program, at=NOW)
    with pytest.raises(MerchantConflict, match="access_denied"):
        app.representative_progress(owner, at=NOW)

    unit.authorization.has_permission.return_value = True
    unit.merchants.create_program.return_value = program
    assert app.configure_program(owner, program=program, at=NOW) == program
    unit.merchants.representative_verified_count.return_value = 3
    assert app.representative_progress(owner, at=NOW) == {"verified_onboardings": 3}

    item = MagicMock()
    item.version = 1
    unit.merchants.get_item.return_value = None
    with pytest.raises(MerchantConflict, match="catalogue_item_not_found"):
        app.set_catalogue_readiness(owner, item_id=uuid4(), ready=True, at=NOW)
    unit.merchants.get_item.return_value = item
    unit.merchants.set_item_state.return_value = item
    assert (
        app.set_catalogue_readiness(owner, item_id=uuid4(), ready=False, at=NOW) is item
    )

    unit.merchants.get_program.return_value = None
    with pytest.raises(MerchantConflict, match="partner_program_not_found"):
        app.enroll_program(
            owner,
            merchant_id=merchant.merchant_id,
            program_id=program.program_id,
            at=NOW,
        )
    unit.merchants.get_program.return_value = program
    unit.merchants.enrollment_count.return_value = 0
    unit.merchants.enroll.side_effect = lambda value: value
    enrollment = app.enroll_program(
        owner, merchant_id=merchant.merchant_id, program_id=program.program_id, at=NOW
    )
    assert enrollment.program_id == program.program_id

    approved = VerificationEvidence(
        merchant_id=merchant.merchant_id,
        kind=VerificationKind.IDENTITY,
        state=VerificationState.APPROVED,
        opaque_reference="verification:opaque:0002",
        submitted_at=NOW,
    )
    unit.merchants.verifications.return_value = (approved,)
    unit.merchants.catalogue_counts.return_value = (1, 1)
    unit.merchants.branch_count.return_value = 1
    unit.merchants.badges.return_value = ("Founding Merchant",)
    dashboard = app.dashboard(owner, merchant_id=merchant.merchant_id, at=NOW)
    assert dashboard.branch_count == 1
    assert dashboard.catalogue_ready == 1


def test_owner_scope_hides_cross_tenant_resources_and_denies_permission() -> None:
    subject = _subject()
    unit = _unit()
    app = MerchantApplication(_Composition(unit))
    unit.merchants.get_profile.return_value = None
    with pytest.raises(MerchantConflict, match="merchant_not_found"):
        app.add_branch(
            subject,
            merchant_id=uuid4(),
            name="Bole Branch",
            address_label="Bole Atlas",
            operating_hours={},
            at=NOW,
        )
    other = _profile(uuid4())
    unit.merchants.get_profile.return_value = other
    with pytest.raises(MerchantConflict, match="merchant_not_found"):
        app.dashboard(subject, merchant_id=other.merchant_id, at=NOW)
    own = _profile(subject.identity_id)
    unit.merchants.get_profile.return_value = own
    unit.authorization.has_permission.return_value = False
    with pytest.raises(MerchantConflict, match="access_denied"):
        app.dashboard(subject, merchant_id=own.merchant_id, at=NOW)
