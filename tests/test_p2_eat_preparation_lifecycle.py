from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from BACKEND.audit.models import ActorType, AuditEvent
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import MerchantState
from BACKEND.merchant_preparation.canonical import (
    CanonicalPreparationAction,
    CanonicalPreparationApplication,
    CanonicalPreparationCase,
    CanonicalPreparationEvidence,
    CanonicalPreparationState,
    PreparationFailureReason,
    ReadinessCorrectionReason,
    preproduction_preparation_policy,
    transition,
)
from BACKEND.merchant_preparation.engine import PreparationConflict

NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def subject(identity_id: UUID) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=IdentityType.MERCHANT,
        actor_type=ActorType.SERVICE,
    )


def case(state: CanonicalPreparationState = CanonicalPreparationState.PENDING):
    return CanonicalPreparationCase(
        decision_case_id=uuid4(),
        decision_evidence_id=uuid4(),
        order_id=uuid4(),
        order_version=3,
        merchant_id=uuid4(),
        merchant_location_id=uuid4(),
        state=state,
        policy_name="AYO_EAT_PREPARATION_POLICY_V1",
        policy_version=1,
        created_at=NOW,
        updated_at=NOW,
    )


class AuditCollector:
    def __init__(self) -> None:
        self.values: list[AuditEvent] = []

    def append(self, value: AuditEvent) -> None:
        self.values.append(value)


class FakePreparationRepository:
    def __init__(self, value: CanonicalPreparationCase, owner: UUID) -> None:
        self.value = value
        self.owner = owner
        self.evidence: CanonicalPreparationEvidence | None = None
        self.reservations: dict[
            tuple[UUID, str, str],
            tuple[tuple[UUID, dict[str, object]], int | None],
        ] = {}
        self.authority: str | None = None

    def get(self, case_id, lock=False):
        return self.value if self.value.preparation_case_id == case_id else None

    def reserve(self, actor, case_id, operation, key, payload, at):
        identity = (actor, operation, key)
        previous = self.reservations.get(identity)
        if previous is not None:
            if previous[0] != (case_id, payload):
                raise PreparationConflict("idempotency_conflict")
            return previous[1], False
        self.reservations[identity] = ((case_id, payload), None)
        return None, True

    def staff_authority(self, merchant, location, staff, action, at):
        return self.authority

    def apply(
        self, current, target, evidence, estimated_ready_at, actor, operation, key
    ):
        self.evidence = evidence
        self.value = current.model_copy(
            update={
                "state": target,
                "version": current.version + 1,
                "estimated_ready_at": estimated_ready_at,
                "updated_at": evidence.occurred_at,
            }
        )
        self.reservations[(actor, operation, key)] = (
            (
                current.preparation_case_id,
                {
                    "case": str(current.preparation_case_id),
                    "version": current.version,
                    "action": operation,
                    "estimate": (
                        None
                        if estimated_ready_at == current.estimated_ready_at
                        else int(
                            (estimated_ready_at - evidence.occurred_at).total_seconds()
                        )
                    ),
                    "failure": (
                        None
                        if evidence.failure_reason is None
                        else evidence.failure_reason.value
                    ),
                    "correction": (
                        None
                        if evidence.correction_reason is None
                        else evidence.correction_reason.value
                    ),
                },
            ),
            self.value.version,
        )
        return self.value


class FakeUnit:
    def __init__(self, repository, owner):
        self.preparation_cases = repository
        self.merchants = SimpleNamespace(
            get_profile=lambda merchant_id, lock=False: SimpleNamespace(
                merchant_id=merchant_id,
                owner_identity_id=owner,
                state=MerchantState.APPROVED,
            )
        )
        self.audit_events = AuditCollector()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeComposition:
    def __init__(self, unit):
        self.unit = unit

    def unit_of_work(self):
        return self.unit


def command(
    application,
    actor,
    value,
    action,
    *,
    estimate=None,
    failure=None,
    correction=None,
    key="preparation-command-0001",
):
    return application.command(
        subject(actor),
        preparation_case_id=value.preparation_case_id,
        expected_version=value.version,
        action=action,
        estimate_seconds=estimate,
        failure_reason=failure,
        correction_reason=correction,
        idempotency_key=key,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )


def test_approved_transition_matrix_rejects_ready_to_unable() -> None:
    assert (
        transition(CanonicalPreparationState.PENDING, CanonicalPreparationAction.START)
        is CanonicalPreparationState.PREPARING
    )
    assert (
        transition(
            CanonicalPreparationState.PREPARING, CanonicalPreparationAction.MARK_READY
        )
        is CanonicalPreparationState.READY
    )
    assert (
        transition(
            CanonicalPreparationState.READY,
            CanonicalPreparationAction.CORRECT_READINESS,
        )
        is CanonicalPreparationState.PREPARING
    )
    with pytest.raises(PreparationConflict, match="transition_not_allowed"):
        transition(
            CanonicalPreparationState.READY,
            CanonicalPreparationAction.DECLARE_UNABLE,
        )


def test_owner_start_records_dual_attribution_evidence_and_audit() -> None:
    owner, value = uuid4(), case()
    repository = FakePreparationRepository(value, owner)
    unit = FakeUnit(repository, owner)
    application = CanonicalPreparationApplication(
        FakeComposition(unit), preproduction_preparation_policy()
    )
    result = command(
        application, owner, value, CanonicalPreparationAction.START, estimate=600
    )
    assert result.state is CanonicalPreparationState.PREPARING
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.authenticated_subject_id == owner
    assert evidence.merchant_owner_identity_id == owner
    assert evidence.authority_basis == "merchant_owner"
    assert len(unit.audit_events.values) == 1


def test_scoped_staff_can_mark_ready_but_unrelated_staff_is_denied() -> None:
    owner, staff = uuid4(), uuid4()
    value = case(CanonicalPreparationState.PREPARING)
    repository = FakePreparationRepository(value, owner)
    unit = FakeUnit(repository, owner)
    application = CanonicalPreparationApplication(
        FakeComposition(unit), preproduction_preparation_policy()
    )
    with pytest.raises(PreparationConflict, match="access_denied"):
        command(application, staff, value, CanonicalPreparationAction.MARK_READY)
    repository.authority = "merchant_staff_preparation_mark_ready"
    result = command(
        application,
        staff,
        value,
        CanonicalPreparationAction.MARK_READY,
        key="preparation-ready-0002",
    )
    assert result.state is CanonicalPreparationState.READY
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.authenticated_subject_id == staff
    assert evidence.merchant_owner_identity_id == owner


def test_unable_requires_closed_reason_and_is_terminal() -> None:
    owner, value = uuid4(), case(CanonicalPreparationState.PREPARING)
    repository = FakePreparationRepository(value, owner)
    application = CanonicalPreparationApplication(
        FakeComposition(FakeUnit(repository, owner)),
        preproduction_preparation_policy(),
    )
    with pytest.raises(PreparationConflict, match="failure_reason_invalid"):
        command(application, owner, value, CanonicalPreparationAction.DECLARE_UNABLE)
    result = command(
        application,
        owner,
        value,
        CanonicalPreparationAction.DECLARE_UNABLE,
        failure=PreparationFailureReason.FOOD_SAFETY_CONSTRAINT,
        key="preparation-unable-0002",
    )
    assert result.state is CanonicalPreparationState.UNABLE
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.failure_reason is (PreparationFailureReason.FOOD_SAFETY_CONSTRAINT)


def test_readiness_correction_is_append_only_and_returns_to_preparing() -> None:
    owner, value = uuid4(), case(CanonicalPreparationState.READY)
    repository = FakePreparationRepository(value, owner)
    application = CanonicalPreparationApplication(
        FakeComposition(FakeUnit(repository, owner)),
        preproduction_preparation_policy(),
    )
    result = command(
        application,
        owner,
        value,
        CanonicalPreparationAction.CORRECT_READINESS,
        correction=ReadinessCorrectionReason.PACKAGING_OR_SEAL,
    )
    assert result.state is CanonicalPreparationState.PREPARING
    evidence = repository.evidence
    assert evidence is not None
    assert evidence.event_type == "commerce.preparation.readiness_corrected"
    assert evidence.from_state is CanonicalPreparationState.READY


def test_actor_scoped_idempotent_retry_returns_same_version() -> None:
    owner, value = uuid4(), case()
    repository = FakePreparationRepository(value, owner)
    application = CanonicalPreparationApplication(
        FakeComposition(FakeUnit(repository, owner)),
        preproduction_preparation_policy(),
    )
    first = command(
        application, owner, value, CanonicalPreparationAction.START, estimate=600
    )
    second = application.command(
        subject(owner),
        preparation_case_id=value.preparation_case_id,
        expected_version=value.version,
        action=CanonicalPreparationAction.START,
        estimate_seconds=600,
        failure_reason=None,
        correction_reason=None,
        idempotency_key="preparation-command-0001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert second.version == first.version
