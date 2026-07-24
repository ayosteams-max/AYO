import os

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, text

from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.config import DatabaseSettings
from BACKEND.persistence.engine import create_postgres_engine
from BACKEND.persistence.kernel import PersistenceKernel
from BACKEND.persistence.tables import (
    AYO_SCHEMA,
    account_password_credentials,
    account_recovery_tokens,
    account_role_assignments,
    account_sessions,
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
    authentication_origin_windows,
    booking_confirmations,
    booking_route_evidence,
    canonical_destinations,
    canonical_pickups,
    canonical_ride_requests,
    canonical_subjects,
    consequence_suppression_decisions,
    credential_verifiers,
    customer_emergency_contacts,
    customer_household_relationships,
    customer_profiles,
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
    financial_hold_events,
    financial_hold_idempotency,
    financial_hold_outbox,
    financial_hold_state_history,
    financial_holds,
    financial_posting_events,
    financial_posting_idempotency,
    financial_posting_lines,
    financial_posting_outbox,
    financial_postings,
    identities,
    identity_accounts,
    identity_authentication_methods,
    identity_devices,
    identity_role_assignments,
    identity_security_bootstrap,
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
    legacy_identity_mappings,
    legacy_wallets,
    localization_pack_manifests,
    localization_preferences,
    marketplace_decisions,
    marketplace_rule_sets,
    marketplace_simulation_runs,
    metadata,
    mobility_availability_evaluations,
    mobility_product_availability,
    mobility_service_area_geometries,
    mobility_service_areas,
    payment_attempts,
    payment_callback_envelopes,
    payment_events,
    payment_idempotency,
    payment_intents,
    payment_outbox,
    permissions,
    persistence_domain_events,
    persistence_idempotency_records,
    persistence_outbox,
    pricing_calculation_components,
    pricing_events,
    pricing_idempotency,
    pricing_outbox,
    pricing_policies,
    rate_limit_buckets,
    reconciliation_exceptions,
    reconciliation_records,
    recovery_cases,
    refresh_token_rotations,
    refund_authorizations,
    refund_decisions,
    refund_events,
    refund_evidence,
    refund_idempotency,
    refund_outbox,
    refund_requests,
    request_access_channel_capabilities,
    request_access_continuity_references,
    request_access_interaction_provenance,
    request_access_source_adapters,
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
    settlement_approvals,
    settlement_batches,
    settlement_events,
    settlement_external_evidence,
    settlement_hold_evidence,
    settlement_idempotency,
    settlement_items,
    settlement_outbox,
    support_ai_interactions,
    support_case_events,
    support_case_messages,
    support_cases,
    token_families,
    waiting_policy_snapshots,
    waiting_session_events,
    waiting_sessions,
    wallet_accounts,
    wallet_events,
    wallet_idempotency,
    wallet_lineage_entries,
    wallet_outbox,
    worker_capability_sessions,
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
        connection.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') "
                "THEN CREATE ROLE ayo_runtime NOLOGIN; END IF; END $$"
            )
        )
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{AYO_SCHEMA}"'))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ayo.mobility_ride_products "
                "(product_code, display_key, created_at) VALUES "
                "('standard', 'mobility.product.standard', now()), "
                "('premium', 'mobility.product.premium', now()), "
                "('airport_transfer', 'mobility.product.airport_transfer', now()), "
                "('accessible_private_ride', "
                "'mobility.product.accessible_private_ride', now()) "
                "ON CONFLICT (product_code) DO NOTHING"
            )
        )
    yield engine
    metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{AYO_SCHEMA}" CASCADE'))
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_postgres_tables(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(delete(request_access_interaction_provenance))
        connection.execute(delete(request_access_continuity_references))
        connection.execute(delete(request_access_channel_capabilities))
        connection.execute(delete(request_access_source_adapters))
        connection.execute(delete(mobility_availability_evaluations))
        connection.execute(delete(mobility_product_availability))
        connection.execute(delete(mobility_service_area_geometries))
        connection.execute(delete(mobility_service_areas))
        connection.execute(delete(customer_emergency_contacts))
        connection.execute(delete(customer_household_relationships))
        connection.execute(delete(customer_profiles))
        connection.execute(delete(ride_request_outbox))
        connection.execute(delete(ride_request_events))
        connection.execute(delete(ride_request_validation_decisions))
        connection.execute(delete(ride_request_idempotency))
        connection.execute(delete(account_role_assignments))
        connection.execute(delete(account_sessions))
        connection.execute(delete(account_password_credentials))
        connection.execute(delete(account_recovery_tokens))
        connection.execute(delete(authentication_origin_windows))
        connection.execute(delete(identity_security_bootstrap))
        connection.execute(delete(legacy_identity_mappings))
        connection.execute(delete(persistence_outbox))
        connection.execute(delete(persistence_domain_events))
        connection.execute(delete(persistence_idempotency_records))
        connection.execute(delete(settlement_external_evidence))
        connection.execute(delete(settlement_hold_evidence))
        connection.execute(delete(settlement_approvals))
        connection.execute(delete(financial_hold_outbox))
        connection.execute(delete(financial_hold_events))
        connection.execute(delete(financial_hold_state_history))
        connection.execute(delete(financial_holds))
        connection.execute(delete(financial_hold_idempotency))
        connection.execute(delete(financial_posting_outbox))
        connection.execute(delete(financial_posting_events))
        connection.execute(delete(financial_posting_lines))
        connection.execute(delete(financial_postings))
        connection.execute(delete(financial_posting_idempotency))
        connection.execute(delete(wallet_outbox))
        connection.execute(delete(wallet_events))
        connection.execute(delete(wallet_lineage_entries))
        connection.execute(delete(wallet_idempotency))
        connection.execute(delete(wallet_accounts))
        connection.execute(delete(settlement_outbox))
        connection.execute(delete(settlement_events))
        connection.execute(delete(reconciliation_exceptions))
        connection.execute(delete(reconciliation_records))
        connection.execute(delete(settlement_items))
        connection.execute(delete(settlement_idempotency))
        connection.execute(delete(settlement_batches))
        connection.execute(delete(refund_outbox))
        connection.execute(delete(refund_events))
        connection.execute(delete(refund_evidence))
        connection.execute(delete(refund_authorizations))
        connection.execute(delete(refund_decisions))
        connection.execute(delete(refund_idempotency))
        connection.execute(delete(refund_requests))
        connection.execute(delete(ledger_outbox))
        connection.execute(delete(ledger_events))
        connection.execute(delete(ledger_entries))
        connection.execute(delete(ledger_journals))
        connection.execute(delete(ledger_idempotency))
        connection.execute(delete(ledger_accounts))
        connection.execute(delete(ledger_books))
        connection.execute(delete(payment_outbox))
        connection.execute(delete(payment_events))
        connection.execute(delete(payment_callback_envelopes))
        connection.execute(delete(payment_attempts))
        connection.execute(delete(payment_idempotency))
        connection.execute(delete(payment_intents))
        connection.execute(delete(pricing_outbox))
        connection.execute(delete(pricing_events))
        connection.execute(delete(pricing_calculation_components))
        connection.execute(delete(fare_calculations))
        connection.execute(delete(fare_estimate_acceptances))
        connection.execute(delete(fare_estimates))
        connection.execute(delete(pricing_idempotency))
        connection.execute(delete(pricing_policies))
        connection.execute(delete(immediate_dispatch_outbox))
        connection.execute(delete(worker_capability_sessions))
        connection.execute(delete(immediate_dispatch_events))
        connection.execute(delete(immediate_dispatch_assignments))
        connection.execute(delete(immediate_dispatch_offers))
        connection.execute(delete(immediate_dispatch_candidate_sets))
        connection.execute(delete(immediate_dispatch_idempotency))
        connection.execute(delete(immediate_dispatch_handoffs))
        connection.execute(delete(localization_preferences))
        connection.execute(delete(localization_pack_manifests))
        connection.execute(delete(booking_confirmations))
        connection.execute(delete(canonical_ride_requests))
        connection.execute(delete(canonical_destinations))
        connection.execute(delete(canonical_pickups))
        connection.execute(delete(booking_route_evidence))
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
        connection.execute(delete(identity_accounts))
        connection.execute(delete(canonical_subjects))
        connection.execute(delete(identities))
        connection.execute(delete(rate_limit_buckets))
        connection.execute(delete(sessions))
        connection.execute(delete(audit_events))
        connection.execute(delete(legacy_wallets))
        connection.execute(delete(rides))
        connection.execute(
            text(
                "INSERT INTO ayo.mobility_ride_products "
                "(product_code, display_key, created_at) VALUES "
                "('standard', 'mobility.product.standard', now()), "
                "('premium', 'mobility.product.premium', now()), "
                "('airport_transfer', 'mobility.product.airport_transfer', now()), "
                "('accessible_private_ride', "
                "'mobility.product.accessible_private_ride', now()) "
                "ON CONFLICT (product_code) DO NOTHING"
            )
        )


@pytest.fixture
def postgres_composition(postgres_engine):
    return PostgresRepositoryComposition(postgres_engine)


@pytest.fixture
def persistence_kernel(postgres_engine):
    return PersistenceKernel(postgres_engine)
