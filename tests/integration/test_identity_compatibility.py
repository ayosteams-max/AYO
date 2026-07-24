from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.identity.compatibility_models import (
    AccountLifecycle,
    LegacySemantic,
    MappingState,
)
from BACKEND.identity.compatibility_service import IdentityCompatibilityService
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.identity_compatibility_repository import (
    LegacyMeaningAmbiguous,
    PostgresIdentityCompatibilityRepository,
)
from BACKEND.persistence.tables import (
    audit_events,
    canonical_subjects,
    identities,
    identity_accounts,
    legacy_identity_mappings,
    persistence_domain_events,
    persistence_outbox,
)
from BACKEND.persistence.trace import TraceContext

pytestmark = [pytest.mark.integration, pytest.mark.identity_compatibility]


def seed_legacy_identity(postgres_engine, *, identity_type="rider", status="active"):
    identity_id = uuid4()
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(identities).values(
                identity_id=identity_id,
                public_id=uuid4(),
                identity_type=identity_type,
                status=status,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
    return identity_id


def trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def map_subject(
    service,
    legacy_identity_id,
    *,
    semantic=LegacySemantic.BUSINESS_PARTICIPANT,
    key="compatibility-map-0001",
):
    return service.map_legacy_subject(
        legacy_identity_id=legacy_identity_id,
        semantic=semantic,
        provenance="approved_classification_v1",
        idempotency_key=key,
        trace=trace(),
    )


def test_rider_mapping_creates_subject_but_never_activates_account(
    postgres_engine,
) -> None:
    legacy_id = seed_legacy_identity(postgres_engine)
    service = IdentityCompatibilityService(postgres_engine)
    subject, mapping = map_subject(service, legacy_id)
    assert subject.subject_kind.value == "human"
    assert mapping.semantic is LegacySemantic.BUSINESS_PARTICIPANT
    assert mapping.mapping_state is MappingState.SUBJECT_MAPPED
    assert mapping.account_id is None
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(identity_accounts)
            ).scalar_one()
            == 0
        )
        legacy = (
            connection.execute(
                select(identities).where(identities.c.identity_id == legacy_id)
            )
            .mappings()
            .one()
        )
    assert legacy["identity_type"] == "rider"
    assert legacy["status"] == "active"


def test_mapping_is_idempotent_and_atomic_with_audit_and_outbox(
    postgres_engine,
) -> None:
    legacy_id = seed_legacy_identity(postgres_engine, identity_type="service")
    service = IdentityCompatibilityService(postgres_engine)
    first = map_subject(
        service,
        legacy_id,
        semantic=LegacySemantic.AUTHORIZATION_PRINCIPAL,
    )
    second = map_subject(
        service,
        legacy_id,
        semantic=LegacySemantic.AUTHORIZATION_PRINCIPAL,
    )
    assert second == first
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(canonical_subjects)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(legacy_identity_mappings)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_domain_events)
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_outbox)
            ).scalar_one()
            == 2
        )


def test_concurrent_mapping_attempts_produce_one_subject(postgres_engine) -> None:
    legacy_id = seed_legacy_identity(postgres_engine, identity_type="service")
    service = IdentityCompatibilityService(postgres_engine)

    def perform(index: int):
        return map_subject(
            service,
            legacy_id,
            semantic=LegacySemantic.AUTHORIZATION_PRINCIPAL,
            key=f"compatibility-map-{index:04d}",
        )[0].subject_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        subject_ids = set(executor.map(perform, (1, 2)))
    assert len(subject_ids) == 1


def test_account_creation_is_explicit_pending_and_retry_safe(postgres_engine) -> None:
    legacy_id = seed_legacy_identity(postgres_engine, identity_type="service")
    service = IdentityCompatibilityService(postgres_engine)
    _, mapping = map_subject(
        service,
        legacy_id,
        semantic=LegacySemantic.AUTHENTICATION_ACTOR,
    )
    first = service.create_account(
        legacy_identity_id=legacy_id,
        expected_mapping_version=mapping.version,
        idempotency_key="compatibility-account-0001",
        trace=trace(),
    )
    second = service.create_account(
        legacy_identity_id=legacy_id,
        expected_mapping_version=mapping.version,
        idempotency_key="compatibility-account-0001",
        trace=trace(),
    )
    assert first == second
    assert first[0].state is AccountLifecycle.PENDING_ACTIVATION
    assert first[1].mapping_state is MappingState.ACCOUNT_MAPPED


def test_business_participant_and_ambiguous_mapping_fail_closed(
    postgres_engine,
) -> None:
    service = IdentityCompatibilityService(postgres_engine)
    rider_id = seed_legacy_identity(postgres_engine)
    _, rider_mapping = map_subject(service, rider_id)
    with pytest.raises(LegacyMeaningAmbiguous):
        service.create_account(
            legacy_identity_id=rider_id,
            expected_mapping_version=rider_mapping.version,
            idempotency_key="compatibility-account-0002",
            trace=trace(),
        )
    with postgres_engine.begin() as connection:
        repository = PostgresIdentityCompatibilityRepository(connection)
        with pytest.raises(LegacyMeaningAmbiguous):
            repository.resolve_authorization_account(rider_id)


def test_account_transition_is_optimistic_and_authorization_requires_active_mapping(
    postgres_engine,
) -> None:
    legacy_id = seed_legacy_identity(postgres_engine, identity_type="service")
    service = IdentityCompatibilityService(postgres_engine)
    _, mapping = map_subject(
        service,
        legacy_id,
        semantic=LegacySemantic.AUTHORIZATION_PRINCIPAL,
    )
    account, _ = service.create_account(
        legacy_identity_id=legacy_id,
        expected_mapping_version=mapping.version,
        idempotency_key="compatibility-account-0003",
        trace=trace(),
    )
    with postgres_engine.begin() as connection:
        repository = PostgresIdentityCompatibilityRepository(connection)
        with pytest.raises(LegacyMeaningAmbiguous):
            repository.resolve_authorization_account(legacy_id)
    active = service.transition_account(
        account_id=account.account_id,
        target=AccountLifecycle.ACTIVE,
        expected_version=account.version,
        idempotency_key="compatibility-state-0001",
        trace=trace(),
    )
    assert active.state is AccountLifecycle.ACTIVE
    with postgres_engine.begin() as connection:
        repository = PostgresIdentityCompatibilityRepository(connection)
        assert repository.resolve_authorization_account(legacy_id) == active
        with pytest.raises(OptimisticConcurrencyError):
            repository.transition_account(
                account,
                target=AccountLifecycle.CLOSED,
                at=datetime.now(UTC),
                expected_version=account.version,
            )


def test_injected_failure_rolls_back_subject_mapping_and_evidence(
    postgres_engine, monkeypatch
) -> None:
    legacy_id = seed_legacy_identity(postgres_engine)
    service = IdentityCompatibilityService(postgres_engine)
    original = PostgresIdentityCompatibilityRepository.map_legacy_subject

    def fail_after_write(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError("injected failure")

    monkeypatch.setattr(
        PostgresIdentityCompatibilityRepository, "map_legacy_subject", fail_after_write
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        map_subject(service, legacy_id)
    with postgres_engine.connect() as connection:
        for table in (
            canonical_subjects,
            legacy_identity_mappings,
            audit_events,
            persistence_domain_events,
            persistence_outbox,
        ):
            assert (
                connection.execute(select(func.count()).select_from(table)).scalar_one()
                == 0
            )


def test_mapping_and_account_survive_new_service_instance(postgres_engine) -> None:
    legacy_id = seed_legacy_identity(postgres_engine, identity_type="service")
    service = IdentityCompatibilityService(postgres_engine)
    _, mapping = map_subject(
        service,
        legacy_id,
        semantic=LegacySemantic.AUTHENTICATION_ACTOR,
    )
    account, _ = service.create_account(
        legacy_identity_id=legacy_id,
        expected_mapping_version=mapping.version,
        idempotency_key="compatibility-account-restart",
        trace=trace(),
    )
    restarted = IdentityCompatibilityService(postgres_engine)
    with restarted._unit_of_work() as unit:  # test-only restart projection
        assert unit.compatibility.get_account(account.account_id) == account
        assert unit.compatibility.get_mapping(legacy_id) is not None
