from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.engine import (
    MerchantConflict,
    assert_program_open,
    readiness,
    verification_requirements,
)
from BACKEND.merchant.models import (
    CatalogueItem,
    CatalogueItemState,
    CatalogueKind,
    MerchantBranch,
    MerchantDashboard,
    MerchantKind,
    MerchantProfile,
    MerchantState,
    OnboardingSource,
    PartnerProgram,
    ProgramEnrollment,
    VerificationEvidence,
    VerificationKind,
    VerificationState,
)


class MerchantApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def register(
        self,
        subject: AuthorizationSubject,
        *,
        legal_name: str,
        display_name: str,
        kind: MerchantKind,
        source: OnboardingSource,
        capability_code: str,
        market_code: str,
        representative_identity_id: UUID | None,
        idempotency_key: str,
        at: datetime,
    ) -> MerchantProfile:
        if subject.identity_type in {IdentityType.ANONYMOUS, IdentityType.SERVICE}:
            raise MerchantConflict("merchant_personal_identity_required")
        if not 16 <= len(idempotency_key) <= 128:
            raise MerchantConflict("idempotency_key_invalid")
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant.register_own", at=at
            ):
                raise MerchantConflict("access_denied")
            if source is not OnboardingSource.SELF and (
                representative_identity_id is None
                or not unit.authorization.has_permission(
                    representative_identity_id, "merchant.assist", at=at
                )
            ):
                raise MerchantConflict("merchant_representative_not_authorized")
            candidate = uuid4()
            merchant_id = unit.merchants.reserve(
                subject.identity_id,
                "merchant.register",
                idempotency_key,
                {
                    "legal_name": legal_name,
                    "display_name": display_name,
                    "kind": kind.value,
                    "source": source.value,
                    "capability_code": capability_code,
                    "market_code": market_code,
                    "representative_identity_id": str(representative_identity_id)
                    if representative_identity_id
                    else None,
                },
                candidate,
                at,
            )
            existing = unit.merchants.get_profile(merchant_id)
            if existing is not None:
                return existing
            value = MerchantProfile(
                merchant_id=merchant_id,
                owner_identity_id=subject.identity_id,
                legal_name=legal_name,
                display_name=display_name,
                kind=kind,
                onboarding_source=source,
                assisted_by_identity_id=representative_identity_id,
                state=MerchantState.DRAFT,
                capability_code=capability_code,
                market_code=market_code,
                created_at=at,
                updated_at=at,
            )
            result = unit.merchants.create_profile(value)
            if representative_identity_id is not None:
                unit.merchants.record_assistance(
                    merchant_id,
                    representative_identity_id,
                    "onboarding_started",
                    False,
                    at,
                )
            return result

    def list_owned(self, subject: AuthorizationSubject) -> tuple[MerchantProfile, ...]:
        with self._composition.unit_of_work() as unit:
            return unit.merchants.list_owned(subject.identity_id)

    def add_branch(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        name: str,
        address_label: str,
        operating_hours: dict[str, str],
        at: datetime,
    ) -> MerchantBranch:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, at=at)
            return unit.merchants.create_branch(
                MerchantBranch(
                    merchant_id=merchant_id,
                    name=name,
                    address_label=address_label,
                    operating_hours=operating_hours,
                    created_at=at,
                )
            )

    def submit_verification(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        kind: VerificationKind,
        opaque_reference: str,
        expires_at: datetime | None,
        at: datetime,
    ) -> VerificationEvidence:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, at=at)
            return unit.merchants.upsert_verification(
                VerificationEvidence(
                    merchant_id=merchant_id,
                    kind=kind,
                    state=VerificationState.SUBMITTED,
                    opaque_reference=opaque_reference,
                    expires_at=expires_at,
                    submitted_at=at,
                )
            )

    def review_verification(
        self,
        subject: AuthorizationSubject,
        *,
        evidence_id: UUID,
        approved: bool,
        reason_code: str | None,
        at: datetime,
    ) -> VerificationEvidence:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant.verification.review", at=at
            ):
                raise MerchantConflict("access_denied")
            evidence = unit.merchants.get_verification(evidence_id, lock=True)
            if evidence is None:
                raise MerchantConflict("merchant_verification_not_found")
            reviewed = unit.merchants.review_verification(
                evidence.model_copy(
                    update={
                        "state": VerificationState.APPROVED
                        if approved
                        else VerificationState.REJECTED,
                        "reviewed_at": at,
                        "reviewed_by_identity_id": subject.identity_id,
                        "reason_code": reason_code,
                    }
                )
            )
            merchant = unit.merchants.get_profile(evidence.merchant_id, lock=True)
            if merchant is None:
                raise MerchantConflict("merchant_not_found")
            states = {
                item.kind: item.state
                for item in unit.merchants.verifications(merchant.merchant_id)
            }
            target = (
                MerchantState.APPROVED
                if all(
                    states.get(kind) is VerificationState.APPROVED
                    for kind in verification_requirements(merchant.capability_code)
                )
                else MerchantState.VERIFICATION_PENDING
            )
            if merchant.state is not target:
                unit.merchants.set_profile_state(
                    merchant.merchant_id,
                    target.value,
                    expected_version=merchant.version,
                    at=at,
                )
            if (
                target is MerchantState.APPROVED
                and merchant.assisted_by_identity_id is not None
            ):
                unit.merchants.record_assistance(
                    merchant.merchant_id,
                    merchant.assisted_by_identity_id,
                    "verified_onboarding",
                    True,
                    at,
                )
            return reviewed

    def add_catalogue_item(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        branch_id: UUID | None,
        kind: CatalogueKind,
        name: str,
        description: str | None,
        category_code: str,
        at: datetime,
    ) -> CatalogueItem:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, at=at)
            if (
                branch_id is not None
                and unit.merchants.get_branch_merchant(branch_id) != merchant_id
            ):
                raise MerchantConflict("merchant_branch_not_found")
            return unit.merchants.create_item(
                CatalogueItem(
                    merchant_id=merchant_id,
                    branch_id=branch_id,
                    kind=kind,
                    name=name,
                    description=description,
                    category_code=category_code,
                    state=CatalogueItemState.DRAFT,
                    created_at=at,
                    updated_at=at,
                )
            )

    def set_catalogue_readiness(
        self, subject: AuthorizationSubject, *, item_id: UUID, ready: bool, at: datetime
    ) -> CatalogueItem:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant.catalogue.review", at=at
            ):
                raise MerchantConflict("access_denied")
            item = unit.merchants.get_item(item_id, lock=True)
            if item is None:
                raise MerchantConflict("merchant_catalogue_item_not_found")
            return unit.merchants.set_item_state(
                item_id,
                CatalogueItemState.READY.value
                if ready
                else CatalogueItemState.REVIEW_REQUIRED.value,
                expected_version=item.version,
                at=at,
            )

    def configure_program(
        self, subject: AuthorizationSubject, *, program: PartnerProgram, at: datetime
    ) -> PartnerProgram:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant.program.manage", at=at
            ):
                raise MerchantConflict("access_denied")
            return unit.merchants.create_program(program)

    def representative_progress(
        self, subject: AuthorizationSubject, *, at: datetime
    ) -> dict[str, int]:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "merchant.assist", at=at
            ):
                raise MerchantConflict("access_denied")
            return {
                "verified_onboardings": unit.merchants.representative_verified_count(
                    subject.identity_id
                )
            }

    def enroll_program(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        program_id: UUID,
        at: datetime,
    ) -> ProgramEnrollment:
        with self._composition.unit_of_work() as unit:
            merchant = self._owner(unit, subject, merchant_id, at=at)
            program = unit.merchants.get_program(program_id, lock=True)
            if (
                program is None
                or program.capability_code != merchant.capability_code
                or program.market_code != merchant.market_code
            ):
                raise MerchantConflict("partner_program_not_found")
            assert_program_open(
                program,
                enrollment_count=unit.merchants.enrollment_count(program_id),
                at=at,
            )
            return unit.merchants.enroll(
                ProgramEnrollment(
                    program_id=program_id, merchant_id=merchant_id, enrolled_at=at
                )
            )

    def dashboard(
        self, subject: AuthorizationSubject, *, merchant_id: UUID, at: datetime
    ) -> MerchantDashboard:
        with self._composition.unit_of_work() as unit:
            merchant = self._owner(
                unit,
                subject,
                merchant_id,
                at=at,
                permission="merchant.dashboard.read_own",
            )
            evidence = unit.merchants.verifications(merchant_id)
            total, ready = unit.merchants.catalogue_counts(merchant_id)
            required = verification_requirements(merchant.capability_code)
            states = tuple(
                next(
                    (e.state for e in evidence if e.kind is kind),
                    VerificationState.REQUIRED,
                )
                for kind in required
            )
            onboarding, verification, catalogue, store_ready = readiness(
                merchant, states, catalogue_total=total, catalogue_ready=ready
            )
            return MerchantDashboard(
                merchant=merchant,
                branch_count=unit.merchants.branch_count(merchant_id),
                verification_complete=sum(
                    s is VerificationState.APPROVED for s in states
                ),
                verification_required=len(states),
                catalogue_ready=ready,
                catalogue_total=total,
                onboarding_percent=onboarding,
                verification_percent=verification,
                catalogue_percent=catalogue,
                store_ready=store_ready,
                program_badges=unit.merchants.badges(merchant_id),
            )

    @staticmethod
    def _owner(
        unit: Any,
        subject: AuthorizationSubject,
        merchant_id: UUID,
        *,
        at: datetime,
        permission: str = "merchant.manage_own",
    ) -> MerchantProfile:
        merchant = unit.merchants.get_profile(
            merchant_id, lock=permission != "merchant.dashboard.read_own"
        )
        if merchant is None or merchant.owner_identity_id != subject.identity_id:
            raise MerchantConflict("merchant_not_found")
        if not unit.authorization.has_permission(
            subject.identity_id, permission, at=at
        ):
            raise MerchantConflict("access_denied")
        return merchant
