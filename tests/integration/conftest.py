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
    arrival_evaluations,
    arrival_notification_evidence,
    arrival_waiting_idempotency,
    audit_events,
    authentication_challenges,
    canonical_destinations,
    canonical_pickups,
    canonical_ride_requests,
    consequence_suppression_decisions,
    credential_verifiers,
    dispatch_assignments,
    dispatch_attempts,
    dispatch_driver_offers,
    dispatch_idempotency_records,
    dispatch_outbox,
    dispatch_ride_requests,
    driver_document_evidence,
    driver_eligibility_decisions,
    driver_onboarding_cases,
    driver_trust_events,
    driver_trust_idempotency,
    driver_trust_outbox,
    driver_vehicle_authorizations,
    driver_vehicles,
    fare_calculations,
    fare_estimate_acceptances,
    fare_estimates,
    identities,
    identity_authentication_methods,
    identity_devices,
    identity_role_assignments,
    immediate_dispatch_assignments,
    immediate_dispatch_candidate_sets,
    immediate_dispatch_events,
    immediate_dispatch_handoffs,
    immediate_dispatch_idempotency,
    immediate_dispatch_offers,
    immediate_dispatch_outbox,
    ledger_accounts,
    ledger_books,
    ledger_entries,
    ledger_events,
    ledger_idempotency,
    ledger_journals,
    ledger_outbox,
    legacy_wallets,
    localization_pack_manifests,
    localization_preferences,
    marketplace_decisions,
    marketplace_rule_sets,
    marketplace_simulation_runs,
    metadata,
    permissions,
    pricing_calculation_components,
    pricing_events,
    pricing_idempotency,
    pricing_outbox,
    pricing_policies,
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
    ride_request_events,
    ride_request_idempotency,
    ride_request_outbox,
    ride_request_validation_decisions,
    ride_reservations,
    rider_readiness_decisions,
    rides,
    role_permissions,
    roles,
    service_zones,
    sessions,
    support_ai_interactions,
    support_case_events,
    support_case_messages,
    support_cases,
    token_families,
    waiting_policy_snapshots,
    waiting_session_events,
    waiting_sessions,
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
        connection.execute(delete(ledger_outbox))
        connection.execute(delete(ledger_events))
        connection.execute(delete(ledger_entries))
        connection.execute(delete(ledger_journals))
        connection.execute(delete(ledger_idempotency))
        connection.execute(delete(ledger_accounts))
        connection.execute(delete(ledger_books))
        connection.execute(delete(pricing_outbox))
        connection.execute(delete(pricing_events))
        connection.execute(delete(pricing_calculation_components))
        connection.execute(delete(fare_calculations))
        connection.execute(delete(fare_estimate_acceptances))
        connection.execute(delete(fare_estimates))
        connection.execute(delete(pricing_idempotency))
        connection.execute(delete(pricing_policies))
        connection.execute(delete(immediate_dispatch_outbox))
        connection.execute(delete(immediate_dispatch_events))
        connection.execute(delete(immediate_dispatch_assignments))
        connection.execute(delete(immediate_dispatch_offers))
        connection.execute(delete(immediate_dispatch_candidate_sets))
        connection.execute(delete(immediate_dispatch_idempotency))
        connection.execute(delete(immediate_dispatch_handoffs))
        connection.execute(delete(localization_preferences))
        connection.execute(delete(localization_pack_manifests))
        connection.execute(delete(ride_request_outbox))
        connection.execute(delete(ride_request_events))
        connection.execute(delete(ride_request_validation_decisions))
        connection.execute(delete(ride_request_idempotency))
        connection.execute(delete(canonical_ride_requests))
        connection.execute(delete(canonical_destinations))
        connection.execute(delete(canonical_pickups))
        connection.execute(delete(service_zones))
        connection.execute(delete(driver_trust_outbox))
        connection.execute(delete(driver_trust_events))
        connection.execute(delete(driver_trust_idempotency))
        connection.execute(delete(driver_eligibility_decisions))
        connection.execute(delete(driver_vehicle_authorizations))
        connection.execute(delete(driver_document_evidence))
        connection.execute(delete(driver_vehicles))
        connection.execute(delete(driver_onboarding_cases))
        connection.execute(delete(arrival_waiting_idempotency))
        connection.execute(delete(consequence_suppression_decisions))
        connection.execute(delete(arrival_notification_evidence))
        connection.execute(delete(waiting_session_events))
        connection.execute(delete(waiting_sessions))
        connection.execute(delete(waiting_policy_snapshots))
        connection.execute(delete(rider_readiness_decisions))
        connection.execute(delete(arrival_evaluations))
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
