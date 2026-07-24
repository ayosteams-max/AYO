from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType, AuditEvent
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import (
    MerchantKind,
    MerchantProfile,
    MerchantState,
    OnboardingSource,
)
from BACKEND.merchant_orders.decision_application import (
    MerchantDecisionApplication,
    preproduction_policy,
)
from BACKEND.merchant_orders.engine import MerchantOrderConflict, decision_transition
from BACKEND.merchant_orders.models import (
    MerchantDecisionCase,
    MerchantDecisionEvidence,
    MerchantDecisionState,
    MerchantRejectionReason,
    MerchantStaffAuthority,
)

NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def decision_case(
    *,
    state: MerchantDecisionState = MerchantDecisionState.PENDING,
    expires_at: datetime = NOW + timedelta(minutes=5),
) -> MerchantDecisionCase:
    return MerchantDecisionCase(
        order_id=uuid4(),
        order_version=1,
        merchant_id=uuid4(),
        merchant_location_id=uuid4(),
        state=state,
        policy_name="AYO_EAT_MERCHANT_DECISION_POLICY_V1",
        policy_version=1,
        window_started_at=expires_at - timedelta(minutes=5),
        expires_at=expires_at,
        created_at=expires_at - timedelta(minutes=5),
        updated_at=expires_at - timedelta(minutes=5),
    )


def merchant(merchant_id: UUID, owner_id: UUID) -> MerchantProfile:
    return MerchantProfile(
        merchant_id=merchant_id,
        owner_identity_id=owner_id,
        legal_name="AYO Test Merchant PLC",
        display_name="AYO Test Merchant",
        kind=MerchantKind.COMPANY,
        onboarding_source=OnboardingSource.SELF,
        state=MerchantState.APPROVED,
        capability_code="merchant.food",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )


class AuditCollector:
    def __init__(self) -> None:
        self.values: list[AuditEvent] = []

    def append(self, value: AuditEvent) -> None:
        self.values.append(value)


class FakeRepository:
    def __init__(
        self,
        case: MerchantDecisionCase,
        profile: MerchantProfile,
        authority: MerchantStaffAuthority | None = None,
    ) -> None:
        self.case = case
        self.profile = profile
        self.authority = authority
        self.evidence: MerchantDecisionEvidence | None = None

    def reserve_decision(self, **_):
        return None, True

    def get_decision_case(self, decision_case_id, *, lock=False):
        del lock
        return self.case if decision_case_id == self.case.decision_case_id else None

    def get_profile(self, merchant_id, *, lock=False):
        del lock
        return self.profile if merchant_id == self.profile.merchant_id else None

    def staff_authority(self, **_):
        return self.authority

    def terminal_decision(
        self,
        current,
        evidence,
        *,
        idempotency_actor_id,
        idempotency_key,
    ):
        del idempotency_actor_id, idempotency_key
        self.evidence = evidence
        self.case = current.model_copy(
            update={
                "state": evidence.result,
                "version": current.version + 1,
                "updated_at": evidence.decided_at,
            }
        )
        return self.case

    def due_decision_cases(self, *, at, limit):
        del at, limit
        return (self.case,)


class FakeUnit:
    def __init__(self, repository: FakeRepository) -> None:
        self.merchant_orders = repository
        self.merchants = repository
        self.audit_events = AuditCollector()
        self.authorization = self

    def has_permission(self, identity_id, permission, *, at):
        del identity_id, permission, at
        return True


class FakeComposition:
    def __init__(self, unit: FakeUnit) -> None:
        self.unit = unit

    class Context:
        def __init__(self, unit):
            self.unit = unit

        def __enter__(self):
            return self.unit

        def __exit__(self, *_):
            return False

    def unit_of_work(self):
        return self.Context(self.unit)


def subject(identity_id: UUID, *, staff: bool = False) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=IdentityType.STAFF if staff else IdentityType.MERCHANT,
        actor_type=ActorType.STAFF if staff else ActorType.SERVICE,
    )


def test_preproduction_policy_is_named_configurable_and_bounded() -> None:
    assert preproduction_policy().maximum_window_seconds == 300
    assert preproduction_policy(120).maximum_window_seconds == 120
    with pytest.raises(ValidationError):
        preproduction_policy(301)


def test_lifecycle_has_one_pending_state_and_three_terminal_outcomes() -> None:
    case = decision_case()
    assert (
        decision_transition(case, MerchantDecisionState.ACCEPTED, at=NOW)
        is MerchantDecisionState.ACCEPTED
    )
    assert (
        decision_transition(case, MerchantDecisionState.REJECTED, at=NOW)
        is MerchantDecisionState.REJECTED
    )
    with pytest.raises(MerchantOrderConflict, match="window_active"):
        decision_transition(case, MerchantDecisionState.EXPIRED, at=NOW)
    assert (
        decision_transition(case, MerchantDecisionState.EXPIRED, at=case.expires_at)
        is MerchantDecisionState.EXPIRED
    )


def test_expiry_is_not_a_rejection_and_late_merchant_decision_fails() -> None:
    expired = decision_case(expires_at=NOW)
    with pytest.raises(MerchantOrderConflict, match="window_expired"):
        decision_transition(expired, MerchantDecisionState.REJECTED, at=NOW)
    assert MerchantDecisionState.EXPIRED.value != MerchantDecisionState.REJECTED.value


def test_owner_acceptance_preserves_dual_attribution_and_evidence() -> None:
    owner_id = uuid4()
    case = decision_case()
    repository = FakeRepository(case, merchant(case.merchant_id, owner_id))
    unit = FakeUnit(repository)
    application = MerchantDecisionApplication(
        FakeComposition(unit), preproduction_policy()
    )
    result = application.decide(
        subject(owner_id),
        decision_case_id=case.decision_case_id,
        expected_version=1,
        result=MerchantDecisionState.ACCEPTED,
        rejection_reason=None,
        idempotency_key="merchant-decision-owner-0001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert result.state is MerchantDecisionState.ACCEPTED
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.authenticated_subject_id == owner_id
    assert evidence.merchant_owner_identity_id == owner_id
    assert evidence.authority_basis == "merchant_owner"
    assert evidence.retention_class == "provisional_regulated_commerce"
    assert len(unit.audit_events.values) == 1


def test_location_scoped_staff_authority_and_closed_rejection_reason() -> None:
    owner_id, staff_id = uuid4(), uuid4()
    case = decision_case()
    authority = MerchantStaffAuthority(
        merchant_id=case.merchant_id,
        merchant_location_id=case.merchant_location_id,
        staff_identity_id=staff_id,
        authority_basis="merchant_staff_order_decision",
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        granted_by_identity_id=owner_id,
        created_at=NOW - timedelta(days=1),
    )
    repository = FakeRepository(case, merchant(case.merchant_id, owner_id), authority)
    application = MerchantDecisionApplication(
        FakeComposition(FakeUnit(repository)), preproduction_policy()
    )
    result = application.decide(
        subject(staff_id, staff=True),
        decision_case_id=case.decision_case_id,
        expected_version=1,
        result=MerchantDecisionState.REJECTED,
        rejection_reason=MerchantRejectionReason.MERCHANT_CAPACITY_EXCEEDED,
        idempotency_key="merchant-decision-staff-0001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert result.state is MerchantDecisionState.REJECTED
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.authenticated_subject_id == staff_id
    assert evidence.merchant_owner_identity_id == owner_id
    assert evidence.rejection_reason is (
        MerchantRejectionReason.MERCHANT_CAPACITY_EXCEEDED
    )


def test_unrelated_staff_is_denied() -> None:
    owner_id = uuid4()
    case = decision_case()
    repository = FakeRepository(case, merchant(case.merchant_id, owner_id))
    application = MerchantDecisionApplication(
        FakeComposition(FakeUnit(repository)), preproduction_policy()
    )
    with pytest.raises(MerchantOrderConflict, match="access_denied"):
        application.decide(
            subject(uuid4(), staff=True),
            decision_case_id=case.decision_case_id,
            expected_version=1,
            result=MerchantDecisionState.ACCEPTED,
            rejection_reason=None,
            idempotency_key="merchant-decision-denied-0001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )


def test_system_expiry_records_no_merchant_actor_or_rejection_reason() -> None:
    owner_id = uuid4()
    case = decision_case(expires_at=NOW)
    repository = FakeRepository(case, merchant(case.merchant_id, owner_id))
    unit = FakeUnit(repository)
    application = MerchantDecisionApplication(
        FakeComposition(unit), preproduction_policy()
    )
    count = application.expire_due(
        AuthorizationSubject(
            identity_id=uuid4(),
            identity_type=IdentityType.SERVICE,
            actor_type=ActorType.SERVICE,
        ),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert count == 1
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.result is MerchantDecisionState.EXPIRED
    assert evidence.authenticated_subject_id is None
    assert evidence.rejection_reason is None
    assert evidence.authority_basis == "system_policy_expiry"
