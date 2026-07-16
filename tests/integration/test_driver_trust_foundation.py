from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.driver_trust.application import (
    DriverTrustAccessDenied,
    DriverTrustApplication,
)
from BACKEND.driver_trust.engine import transition_case
from BACKEND.driver_trust.models import (
    DocumentEvidence,
    EvidenceStatus,
    EvidenceType,
    OnboardingCase,
    OnboardingState,
)
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.persistence.driver_trust_repository import ConcurrentDriverTrustChange
from BACKEND.persistence.tables import driver_trust_outbox

pytestmark = [pytest.mark.integration, pytest.mark.authorization]
NOW = datetime(2026, 7, 16, tzinfo=UTC)


def create_driver(composition):
    identity = Identity(
        public_id=uuid4(),
        identity_type=IdentityType.DRIVER,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    with composition.unit_of_work() as unit:
        return unit.identities.create(identity)


def test_case_is_durable_owned_and_transition_is_optimistic(
    postgres_composition,
) -> None:
    driver = create_driver(postgres_composition)
    original = OnboardingCase(
        driver_identity_id=driver.identity_id,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        stored = unit.driver_trust.create_case(original)
        assert (
            unit.driver_trust.owner_identity_id(
                resource_type="driver_onboarding_case", resource_id=str(stored.case_id)
            )
            == driver.identity_id
        )
    changed = transition_case(
        original, OnboardingState.CONTACT_VERIFICATION_PENDING, at=NOW
    )
    with postgres_composition.unit_of_work() as unit:
        assert unit.driver_trust.save_case(changed, expected_version=1).version == 2
    with (
        pytest.raises(ConcurrentDriverTrustChange),
        postgres_composition.unit_of_work() as unit,
    ):
        unit.driver_trust.save_case(changed, expected_version=1)


def test_cross_driver_access_and_unauthorized_review_are_denied_safely(
    postgres_composition,
) -> None:
    owner = create_driver(postgres_composition)
    attacker = create_driver(postgres_composition)
    onboarding = OnboardingCase(
        driver_identity_id=owner.identity_id,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        unit.driver_trust.create_case(onboarding)
    subject = AuthorizationSubject(
        identity_id=attacker.identity_id,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )
    application = DriverTrustApplication(postgres_composition)
    with pytest.raises(DriverTrustAccessDenied, match="resource_access_denied"):
        application.get_own_case(subject=subject, case_id=onboarding.case_id)
    with pytest.raises(DriverTrustAccessDenied, match="access_denied"):
        application.review_transition(
            subject=subject,
            case_id=onboarding.case_id,
            target=OnboardingState.CONTACT_VERIFICATION_PENDING,
            reason_code="review.approved",
            at=NOW,
        )


def test_evidence_review_records_server_reviewer_and_rejects_stale_decision(
    postgres_composition,
) -> None:
    driver = create_driver(postgres_composition)
    reviewer = create_driver(postgres_composition)
    onboarding = OnboardingCase(
        driver_identity_id=driver.identity_id,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )
    item = DocumentEvidence(
        case_id=onboarding.case_id,
        driver_identity_id=driver.identity_id,
        evidence_type=EvidenceType.DRIVER_LICENCE,
        immutable_reference=f"vault://metadata/{uuid4()}",
        issuing_authority_code="ethiopia.authority.pending",
        document_reference_hash=uuid4().bytes + uuid4().bytes,
        issue_date=date(2025, 1, 1),
        expiry_date=date(2027, 1, 1),
        policy_version="identity.v1",
        submitted_at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        unit.driver_trust.create_case(onboarding)
        unit.driver_trust.add_evidence(item)
    with postgres_composition.unit_of_work() as unit:
        reviewed = unit.driver_trust.review_evidence(
            item.evidence_id,
            status=EvidenceStatus.APPROVED,
            reviewer_identity_id=reviewer.identity_id,
            reason_codes=("document.valid",),
            reviewed_at=NOW,
            expected_version=1,
        )
        assert reviewed.reviewer_identity_id == reviewer.identity_id
        assert reviewed.version == 2
    with (
        pytest.raises(ConcurrentDriverTrustChange),
        postgres_composition.unit_of_work() as unit,
    ):
        unit.driver_trust.review_evidence(
            item.evidence_id,
            status=EvidenceStatus.REJECTED,
            reviewer_identity_id=uuid4(),
            reason_codes=("document.invalid",),
            reviewed_at=NOW,
            expected_version=1,
        )


def test_idempotency_replay_and_mismatch(postgres_composition) -> None:
    actor, response = uuid4(), uuid4()
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.driver_trust.reserve_idempotency(
                actor_identity_id=actor,
                key="submit-1",
                operation="evidence.submit",
                request_hash="a" * 64,
                response_reference=response,
                created_at=NOW,
            )
            == response
        )
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.driver_trust.reserve_idempotency(
                actor_identity_id=actor,
                key="submit-1",
                operation="evidence.submit",
                request_hash="a" * 64,
                response_reference=uuid4(),
                created_at=NOW,
            )
            == response
        )
    with (
        pytest.raises(ValueError, match="different request"),
        postgres_composition.unit_of_work() as unit,
    ):
        unit.driver_trust.reserve_idempotency(
            actor_identity_id=actor,
            key="submit-1",
            operation="evidence.submit",
            request_hash="b" * 64,
            response_reference=uuid4(),
            created_at=NOW,
        )


def test_outbox_rolls_back_atomically(postgres_composition) -> None:
    event_id = uuid4()
    with (
        pytest.raises(RuntimeError),
        postgres_composition.unit_of_work() as unit,
    ):
        unit.connection.execute(
            insert(driver_trust_outbox).values(
                event_id=event_id,
                event_type="driver_trust.changed",
                aggregate_id=uuid4(),
                payload={},
                created_at=NOW,
                available_at=NOW,
                attempt_count=0,
            )
        )
        raise RuntimeError("rollback")
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(driver_trust_outbox.c.event_id).where(
                    driver_trust_outbox.c.event_id == event_id
                )
            ).scalar_one_or_none()
            is None
        )


def test_concurrent_idempotency_has_one_authoritative_record(
    postgres_composition,
) -> None:
    actor, response = uuid4(), uuid4()

    def submit():
        with postgres_composition.unit_of_work() as unit:
            return unit.driver_trust.reserve_idempotency(
                actor_identity_id=actor,
                key="race",
                operation="case.create",
                request_hash="c" * 64,
                response_reference=response,
                created_at=NOW,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result() for future in [pool.submit(submit), pool.submit(submit)]
        ]
    assert results == [response, response]
