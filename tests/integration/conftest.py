import os

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, text

from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.config import DatabaseSettings
from BACKEND.persistence.engine import create_postgres_engine
from BACKEND.persistence.tables import (
    AYO_SCHEMA,
    active_ride_confidence_decisions,
    active_ride_events,
    active_ride_evidence,
    active_ride_idempotency_records,
    active_ride_pickup_recommendations,
    active_ride_pickup_verifications,
    active_ride_projection_checkpoints,
    active_ride_recovery_checkpoints,
    active_rides,
    audit_events,
    authentication_challenges,
    credential_verifiers,
    dispatch_assignments,
    dispatch_attempts,
    dispatch_driver_offers,
    dispatch_idempotency_records,
    dispatch_outbox,
    dispatch_ride_requests,
    identities,
    identity_authentication_methods,
    identity_devices,
    identity_role_assignments,
    legacy_wallets,
    marketplace_decisions,
    marketplace_rule_sets,
    marketplace_simulation_runs,
    metadata,
    permissions,
    rate_limit_buckets,
    recovery_cases,
    refresh_token_rotations,
    reservation_attempts,
    reservation_checkpoints,
    reservation_consents,
    reservation_driver_commitments,
    reservation_flight_context,
    reservation_idempotency_records,
    reservation_participants,
    reservation_pickup_verifications,
    reservation_planning_cycles,
    reservation_soft_plans,
    reservation_state_history,
    ride_reservations,
    rides,
    role_permissions,
    roles,
    sessions,
    support_ai_interactions,
    support_case_events,
    support_case_messages,
    support_cases,
    token_families,
)


@pytest.fixture(scope="session")
def postgres_engine():
    database_url = os.getenv("AYO_TEST_DATABASE_URL")
    if not database_url:
        if os.getenv("CI", "").lower() == "true":
            pytest.fail(
                "AYO_TEST_DATABASE_URL is mandatory in CI; integration tests "
                "must not be skipped."
            )
        pytest.skip(
            "AYO_TEST_DATABASE_URL is required for PostgreSQL integration tests"
        )

    settings = DatabaseSettings(
        url=SecretStr(database_url),
        ssl_mode="disable",
        application_name="ayo-integration-tests",
        pool_size=3,
        max_overflow=1,
    )
    engine = create_postgres_engine(settings)
    with engine.connect() as connection:
        server_version = connection.execute(
            text("SHOW server_version_num")
        ).scalar_one()
        assert 170_000 <= int(server_version) < 180_000

    # Test-only schema setup. Production startup must never call create_all().
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{AYO_SCHEMA}"'))
    metadata.create_all(engine)
    yield engine
    metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{AYO_SCHEMA}" CASCADE'))
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_postgres_tables(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(delete(active_ride_recovery_checkpoints))
        connection.execute(delete(active_ride_pickup_recommendations))
        connection.execute(delete(active_ride_confidence_decisions))
        connection.execute(delete(active_ride_evidence))
        connection.execute(delete(active_ride_pickup_verifications))
        connection.execute(delete(active_ride_projection_checkpoints))
        connection.execute(delete(active_ride_idempotency_records))
        connection.execute(delete(active_ride_events))
        connection.execute(delete(active_rides))
        connection.execute(delete(reservation_pickup_verifications))
        connection.execute(delete(reservation_idempotency_records))
        connection.execute(delete(reservation_checkpoints))
        connection.execute(delete(reservation_attempts))
        connection.execute(delete(reservation_soft_plans))
        connection.execute(delete(reservation_driver_commitments))
        connection.execute(delete(reservation_planning_cycles))
        connection.execute(delete(reservation_state_history))
        connection.execute(delete(reservation_consents))
        connection.execute(delete(reservation_flight_context))
        connection.execute(delete(reservation_participants))
        connection.execute(delete(ride_reservations))
        connection.execute(delete(marketplace_simulation_runs))
        connection.execute(delete(marketplace_decisions))
        connection.execute(delete(marketplace_rule_sets))
        connection.execute(delete(dispatch_outbox))
        connection.execute(delete(dispatch_idempotency_records))
        connection.execute(delete(dispatch_assignments))
        connection.execute(delete(dispatch_driver_offers))
        connection.execute(delete(dispatch_attempts))
        connection.execute(delete(dispatch_ride_requests))
        connection.execute(delete(support_ai_interactions))
        connection.execute(delete(support_case_messages))
        connection.execute(delete(support_case_events))
        connection.execute(delete(support_cases))
        connection.execute(delete(identity_role_assignments))
        connection.execute(delete(role_permissions))
        connection.execute(delete(roles))
        connection.execute(delete(permissions))
        connection.execute(delete(refresh_token_rotations))
        connection.execute(delete(token_families))
        connection.execute(delete(recovery_cases))
        connection.execute(delete(credential_verifiers))
        connection.execute(delete(authentication_challenges))
        connection.execute(delete(identity_devices))
        connection.execute(delete(identity_authentication_methods))
        connection.execute(delete(identities))
        connection.execute(delete(rate_limit_buckets))
        connection.execute(delete(sessions))
        connection.execute(delete(audit_events))
        connection.execute(delete(legacy_wallets))
        connection.execute(delete(rides))


@pytest.fixture
def postgres_composition(postgres_engine):
    return PostgresRepositoryComposition(postgres_engine)
