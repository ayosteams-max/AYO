from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType, AuditEvent
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.courier_dispatch.application import CourierDispatchApplication
from BACKEND.courier_dispatch.engine import (
    CourierDispatchConflict,
    DispatchPolicy,
    target_state,
)
from BACKEND.courier_dispatch.models import (
    CourierAssignment,
    CourierAssignmentState,
    CourierDispatchAction,
    CourierDispatchRequest,
    CourierDispatchState,
    CourierEligibilityEvidence,
    CourierOffer,
    CourierOfferState,
    EligibilityEvidenceType,
    MerchantCourierDispatchView,
)
from BACKEND.custody.models import CustodyState
from BACKEND.identity.models import IdentityType
from BACKEND.routes.courier_dispatch import CourierDispatchCommand

NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def eligibility(
    *,
    eligible: bool = True,
    expires: datetime | None = None,
) -> tuple[CourierEligibilityEvidence, ...]:
    return tuple(
        CourierEligibilityEvidence(
            evidence_type=evidence_type,
            source_reference=uuid4(),
            source_version=3,
            eligible=eligible,
            observed_at=NOW - timedelta(seconds=5),
            valid_until=expires or NOW + timedelta(minutes=5),
        )
        for evidence_type in reversed(tuple(EligibilityEvidenceType))
    )


def dispatch_request(
    *,
    state: CourierDispatchState = CourierDispatchState.WAITING,
    version: int = 1,
    offered_courier=None,
) -> CourierDispatchRequest:
    return CourierDispatchRequest(
        dispatch_id=uuid4(),
        order_id=uuid4(),
        merchant_id=uuid4(),
        readiness_message_id=uuid4(),
        state=state,
        version=version,
        policy_code="AYO_COURIER_DISPATCH_POLICY_V1",
        policy_version=1,
        offered_courier_identity_id=offered_courier,
        assigned_courier_identity_id=None,
        created_at=NOW,
        offered_at=NOW if offered_courier else None,
        assigned_at=None,
        updated_at=NOW,
    )


def subject(identity_id=None) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id or uuid4(),
        identity_type=IdentityType.SERVICE,
        actor_type=ActorType.SERVICE,
    )


class AuditCollector:
    def __init__(self) -> None:
        self.values: list[AuditEvent] = []

    def append(self, value: AuditEvent) -> None:
        self.values.append(value)


class FakeDispatchRepository:
    def __init__(self, value: CourierDispatchRequest) -> None:
        self.value = value
        self.reserved: dict[
            tuple[UUID, CourierDispatchAction, str],
            tuple[tuple[UUID, int], MerchantCourierDispatchView | None],
        ] = {}
        self.evidence: tuple[CourierEligibilityEvidence, ...] | None = None

    def get(self, dispatch_id, lock=False):
        return self.value if self.value.dispatch_id == dispatch_id else None

    def reserve(self, actor_id, dispatch_id, key, action, expected_version, at):
        identity = (actor_id, action, key)
        previous = self.reserved.get(identity)
        if previous is not None:
            if previous[0] != (dispatch_id, expected_version):
                raise CourierDispatchConflict("idempotency_conflict")
            return previous[1]
        self.reserved[identity] = ((dispatch_id, expected_version), None)
        return None

    def offer(
        self,
        current,
        courier_id,
        actor_id,
        target,
        key,
        evidence,
        expires_at,
        correlation_id,
        causation_id,
        at,
    ):
        self.evidence = evidence
        self.value = current.model_copy(
            update={
                "state": target,
                "version": current.version + 1,
                "attempt_number": current.attempt_number + 1,
                "active_offer_id": uuid4(),
                "offered_courier_identity_id": courier_id,
                "offered_at": at,
                "updated_at": at,
            }
        )
        result = MerchantCourierDispatchView(dispatch=self.value, events=())
        self.reserved[(actor_id, CourierDispatchAction.OFFER, key)] = (
            (current.dispatch_id, current.version),
            result,
        )
        return result

    def respond_offer(
        self,
        current,
        courier_id,
        action,
        target,
        key,
        at,
        correlation_id,
        causation_id,
    ):
        self.value = current.model_copy(
            update={
                "state": target,
                "version": current.version + 1,
                "offered_courier_identity_id": None,
                "active_offer_id": None,
                "updated_at": at,
            }
        )
        result = MerchantCourierDispatchView(dispatch=self.value, events=())
        self.reserved[(courier_id, action, key)] = (
            (current.dispatch_id, current.version),
            result,
        )
        return result


class FakeAuthorization:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def has_permission(self, identity_id, permission, at):
        return self.allowed


class FakeUnit:
    def __init__(self, repository, allowed=True) -> None:
        self.courier_dispatch = repository
        self.authorization = FakeAuthorization(allowed)
        self.audit_events = AuditCollector()
        self.custody = SimpleNamespace(get_by_order=lambda order_id: None)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeComposition:
    def __init__(self, unit) -> None:
        self.unit = unit

    def unit_of_work(self):
        return self.unit


def test_dispatch_policy_v1_is_named_versioned_and_deterministic() -> None:
    policy = DispatchPolicy()
    first = policy.evaluate(eligibility(), at=NOW)
    second = policy.evaluate(tuple(reversed(eligibility())), at=NOW)
    assert policy.code == "AYO_COURIER_DISPATCH_POLICY_V1"
    assert policy.version == 1
    assert [item.evidence_type for item in first] == sorted(
        EligibilityEvidenceType, key=lambda value: value.value
    )
    assert [item.evidence_type for item in second] == [
        item.evidence_type for item in first
    ]
    assert policy.expires_at(NOW) == NOW + timedelta(seconds=120)


def test_eligibility_fails_closed_for_missing_stale_or_negative_evidence() -> None:
    policy = DispatchPolicy()
    with pytest.raises(
        CourierDispatchConflict, match="courier_eligibility_evidence_incomplete"
    ):
        policy.evaluate(eligibility()[:-1], at=NOW)
    with pytest.raises(CourierDispatchConflict, match="courier_ineligible"):
        policy.evaluate(eligibility(eligible=False), at=NOW)
    with pytest.raises(CourierDispatchConflict, match="courier_ineligible"):
        policy.evaluate(eligibility(expires=NOW), at=NOW)


@pytest.mark.parametrize(
    ("state", "action", "target"),
    [
        (
            CourierDispatchState.WAITING,
            CourierDispatchAction.OFFER,
            CourierDispatchState.OFFERED,
        ),
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.ACCEPT,
            CourierDispatchState.ASSIGNED,
        ),
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.DECLINE,
            CourierDispatchState.WAITING,
        ),
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.EXPIRE,
            CourierDispatchState.WAITING,
        ),
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.REVOKE,
            CourierDispatchState.WAITING,
        ),
        (
            CourierDispatchState.ASSIGNED,
            CourierDispatchAction.RELEASE,
            CourierDispatchState.WAITING,
        ),
        (
            CourierDispatchState.WAITING,
            CourierDispatchAction.CANCEL,
            CourierDispatchState.CANCELLED,
        ),
        (
            CourierDispatchState.OFFERED,
            CourierDispatchAction.CANCEL,
            CourierDispatchState.CANCELLED,
        ),
        (
            CourierDispatchState.ASSIGNED,
            CourierDispatchAction.CANCEL,
            CourierDispatchState.CANCELLED,
        ),
        (
            CourierDispatchState.WAITING,
            CourierDispatchAction.CONCLUDE_UNFULFILLED,
            CourierDispatchState.UNFULFILLED,
        ),
    ],
)
def test_approved_dispatch_transition_matrix(
    state: CourierDispatchState,
    action: CourierDispatchAction,
    target: CourierDispatchState,
) -> None:
    assert target_state(state, action) is target


def test_terminal_dispatch_states_reject_further_actions() -> None:
    for state in (
        CourierDispatchState.CANCELLED,
        CourierDispatchState.UNFULFILLED,
    ):
        with pytest.raises(
            CourierDispatchConflict, match="invalid_courier_dispatch_transition"
        ):
            target_state(state, CourierDispatchAction.OFFER)


def test_offer_has_one_explicit_terminal_state_and_assignment_is_separate() -> None:
    dispatch_id, courier_id, offer_id = uuid4(), uuid4(), uuid4()
    offer = CourierOffer(
        offer_id=offer_id,
        dispatch_id=dispatch_id,
        attempt_number=1,
        courier_identity_id=courier_id,
        state=CourierOfferState.ACCEPTED,
        offered_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
        resolved_at=NOW + timedelta(seconds=20),
        resolution_actor_identity_id=courier_id,
        resolution_reason="accepted",
        version=2,
    )
    assert offer.resolved_at is not None
    assignment = CourierAssignment(
        assignment_id=uuid4(),
        dispatch_id=dispatch_id,
        offer_id=offer.offer_id,
        attempt_number=1,
        courier_identity_id=courier_id,
        state=CourierAssignmentState.ASSIGNED,
        assigned_at=offer.resolved_at,
        version=1,
    )
    assert offer.state is CourierOfferState.ACCEPTED
    assert assignment.state is CourierAssignmentState.ASSIGNED
    assert assignment.offer_id == offer.offer_id


def test_reassignment_preserves_prior_assignment_evidence() -> None:
    dispatch_id, courier_id, offer_id = uuid4(), uuid4(), uuid4()
    first = CourierAssignment(
        assignment_id=uuid4(),
        dispatch_id=dispatch_id,
        offer_id=offer_id,
        attempt_number=1,
        courier_identity_id=courier_id,
        state=CourierAssignmentState.RELEASED,
        assigned_at=NOW,
        closed_at=NOW + timedelta(minutes=1),
        close_reason="courier_unavailable_before_pickup",
        version=2,
    )
    second = CourierAssignment(
        assignment_id=uuid4(),
        dispatch_id=dispatch_id,
        offer_id=uuid4(),
        attempt_number=2,
        courier_identity_id=uuid4(),
        state=CourierAssignmentState.ASSIGNED,
        assigned_at=NOW + timedelta(minutes=2),
        version=1,
    )
    assert first.assignment_id != second.assignment_id
    assert first.attempt_number < second.attempt_number
    assert first.state is CourierAssignmentState.RELEASED


def test_only_accept_and_decline_are_customer_adapter_commands() -> None:
    assert (
        CourierDispatchCommand(
            expected_version=2, action=CourierDispatchAction.ACCEPT
        ).courier_action
        is CourierDispatchAction.ACCEPT
    )
    assert (
        CourierDispatchCommand(
            expected_version=2, action=CourierDispatchAction.DECLINE
        ).courier_action
        is CourierDispatchAction.DECLINE
    )
    with pytest.raises(
        CourierDispatchConflict, match="offer_requires_dispatch_authority"
    ):
        _ = CourierDispatchCommand(
            expected_version=2, action=CourierDispatchAction.REVOKE
        ).courier_action


def test_eligibility_model_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        CourierEligibilityEvidence(
            evidence_type=EligibilityEvidenceType.AVAILABILITY,
            source_reference=uuid4(),
            source_version=1,
            eligible=True,
            observed_at=datetime(2026, 7, 23, 12),
            valid_until=NOW,
        )


def test_offer_requires_least_privilege_and_records_audit_and_source_evidence() -> None:
    value = dispatch_request()
    repository = FakeDispatchRepository(value)
    denied = FakeUnit(repository, allowed=False)
    application = CourierDispatchApplication(FakeComposition(denied), DispatchPolicy())
    actor = subject()
    with pytest.raises(CourierDispatchConflict, match="access_denied"):
        application.offer_courier(
            actor,
            dispatch_id=value.dispatch_id,
            expected_version=1,
            eligible_courier_identity_id=uuid4(),
            eligibility_evidence=eligibility(),
            idempotency_key="dispatch-offer-0000001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )

    unit = FakeUnit(repository)
    application = CourierDispatchApplication(FakeComposition(unit), DispatchPolicy())
    result = application.offer_courier(
        actor,
        dispatch_id=value.dispatch_id,
        expected_version=1,
        eligible_courier_identity_id=uuid4(),
        eligibility_evidence=eligibility(),
        idempotency_key="dispatch-offer-0000002",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert result.dispatch.state is CourierDispatchState.OFFERED
    evidence = repository.evidence
    assert evidence is not None
    assert len(evidence) == len(EligibilityEvidenceType)
    assert len(unit.audit_events.values) == 1


def test_decline_is_actor_scoped_idempotent_and_never_assigns() -> None:
    courier_id = uuid4()
    value = dispatch_request(
        state=CourierDispatchState.OFFERED,
        version=2,
        offered_courier=courier_id,
    ).model_copy(update={"active_offer_id": uuid4(), "attempt_number": 1})
    repository = FakeDispatchRepository(value)
    unit = FakeUnit(repository)
    application = CourierDispatchApplication(FakeComposition(unit), DispatchPolicy())
    actor = subject(courier_id)
    first = application.command(
        actor,
        dispatch_id=value.dispatch_id,
        expected_version=2,
        action=CourierDispatchAction.DECLINE,
        courier_identity_id=courier_id,
        idempotency_key="dispatch-decline-00001",
        at=NOW,
    )
    second = application.command(
        actor,
        dispatch_id=value.dispatch_id,
        expected_version=2,
        action=CourierDispatchAction.DECLINE,
        courier_identity_id=courier_id,
        idempotency_key="dispatch-decline-00001",
        at=NOW,
    )
    assert first.dispatch.state is CourierDispatchState.WAITING
    assert second.dispatch.version == first.dispatch.version
    assert first.dispatch.assigned_courier_identity_id is None
    assert len(unit.audit_events.values) == 1


def test_dispatch_authority_ends_after_custody_acceptance() -> None:
    value = dispatch_request(state=CourierDispatchState.ASSIGNED, version=3).model_copy(
        update={
            "active_assignment_id": uuid4(),
            "assigned_courier_identity_id": uuid4(),
        }
    )
    repository = FakeDispatchRepository(value)
    unit = FakeUnit(repository)
    unit.custody = SimpleNamespace(
        get_by_order=lambda order_id: SimpleNamespace(
            custody=SimpleNamespace(state=CustodyState.ACCEPTED)
        )
    )
    application = CourierDispatchApplication(FakeComposition(unit), DispatchPolicy())
    with pytest.raises(
        CourierDispatchConflict, match="dispatch_authority_ended_at_custody"
    ):
        application.authority_command(
            subject(),
            dispatch_id=value.dispatch_id,
            expected_version=value.version,
            action=CourierDispatchAction.RELEASE,
            idempotency_key="dispatch-release-00001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            reason="courier_unavailable_before_pickup",
            at=NOW,
        )
