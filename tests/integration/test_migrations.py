from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from BACKEND.authorization.registry import PERMISSION_REGISTRY
from BACKEND.persistence.migrations import (
    MIGRATION_LOCK_ID,
    MigrationLockTimeout,
    MigrationRunner,
    SchemaVersionReadinessChecker,
    alembic_config,
    expected_schema_revision,
)
from BACKEND.persistence.tables import AYO_SCHEMA, VERSION_TABLE, metadata

pytestmark = [pytest.mark.integration, pytest.mark.migration]


@pytest.fixture
def empty_database(postgres_engine, clean_postgres_tables):
    with postgres_engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{AYO_SCHEMA}" CASCADE'))
        connection.execute(text(f'DROP TABLE IF EXISTS public."{VERSION_TABLE}"'))
    yield
    with postgres_engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{AYO_SCHEMA}" CASCADE'))
        connection.execute(text(f'DROP TABLE IF EXISTS public."{VERSION_TABLE}"'))
        connection.execute(text(f'CREATE SCHEMA "{AYO_SCHEMA}"'))
    metadata.create_all(postgres_engine)


def test_upgrade_empty_database_matches_metadata_and_postgresql_17(
    postgres_engine, empty_database
) -> None:
    with postgres_engine.connect() as connection:
        version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
        extensions_before = set(
            connection.execute(text("SELECT extname FROM pg_extension")).scalars()
        )

    MigrationRunner(postgres_engine).upgrade()

    readiness = SchemaVersionReadinessChecker(postgres_engine).check()
    assert 170_000 <= version < 180_000
    assert readiness.ready
    assert readiness.current_revision == expected_schema_revision()
    assert set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA)) == {
        "active_rides",
        "pricing_policies",
        "fare_estimates",
        "fare_estimate_acceptances",
        "fare_calculations",
        "pricing_calculation_components",
        "pricing_idempotency",
        "pricing_events",
        "pricing_outbox",
        "active_ride_events",
        "active_ride_idempotency_records",
        "active_ride_projection_checkpoints",
        "active_ride_pickup_verifications",
        "active_ride_evidence",
        "active_ride_confidence_decisions",
        "active_ride_pickup_recommendations",
        "active_ride_recovery_checkpoints",
        "arrival_evaluations",
        "rider_readiness_decisions",
        "waiting_policy_snapshots",
        "waiting_sessions",
        "waiting_session_events",
        "arrival_notification_evidence",
        "consequence_suppression_decisions",
        "arrival_waiting_idempotency",
        "audit_events",
        "authentication_challenges",
        "credential_verifiers",
        "dispatch_assignments",
        "dispatch_attempts",
        "dispatch_driver_offers",
        "dispatch_idempotency_records",
        "dispatch_outbox",
        "dispatch_ride_requests",
        "driver_document_evidence",
        "driver_eligibility_decisions",
        "driver_onboarding_cases",
        "driver_trust_events",
        "driver_trust_idempotency",
        "driver_trust_outbox",
        "driver_vehicle_authorizations",
        "driver_vehicles",
        "canonical_destinations",
        "canonical_pickups",
        "canonical_ride_requests",
        "identities",
        "immediate_dispatch_assignments",
        "immediate_dispatch_candidate_sets",
        "immediate_dispatch_events",
        "immediate_dispatch_handoffs",
        "immediate_dispatch_idempotency",
        "immediate_dispatch_offers",
        "immediate_dispatch_outbox",
        "identity_authentication_methods",
        "identity_devices",
        "identity_role_assignments",
        "legacy_wallets",
        "localization_pack_manifests",
        "localization_preferences",
        "marketplace_decisions",
        "marketplace_rule_sets",
        "marketplace_simulation_runs",
        "ride_reservations",
        "reservation_participants",
        "reservation_consents",
        "reservation_state_history",
        "reservation_planning_cycles",
        "reservation_driver_commitments",
        "reservation_soft_plans",
        "reservation_attempts",
        "reservation_checkpoints",
        "reservation_flight_context",
        "reservation_idempotency_records",
        "reservation_pickup_verifications",
        "rate_limit_buckets",
        "recovery_cases",
        "refresh_token_rotations",
        "rides",
        "ride_request_events",
        "ride_request_idempotency",
        "ride_request_outbox",
        "ride_request_validation_decisions",
        "role_permissions",
        "roles",
        "sessions",
        "service_zones",
        "token_families",
        "permissions",
        "support_cases",
        "support_case_events",
        "support_case_messages",
        "support_ai_interactions",
    }
    with postgres_engine.connect() as connection:
        extensions_after = set(
            connection.execute(text("SELECT extname FROM pg_extension")).scalars()
        )
        context = MigrationContext.configure(
            connection,
            opts={
                "include_schemas": True,
                "include_object": lambda obj, name, type_, reflected, compare_to: (
                    not (reflected and type_ == "table" and name == VERSION_TABLE)
                ),
            },
        )
        assert compare_metadata(context, metadata) == []
        registered_permissions = set(
            connection.execute(text("SELECT code FROM ayo.permissions")).scalars()
        )
        assert registered_permissions == set(PERMISSION_REGISTRY)
    assert extensions_after == extensions_before | {"btree_gist"}


def test_runtime_role_has_append_read_but_not_mutation_privileges(
    postgres_engine, empty_database
) -> None:
    with postgres_engine.begin() as connection:
        connection.execute(text("DROP ROLE IF EXISTS ayo_runtime"))
        connection.execute(text("CREATE ROLE ayo_runtime NOLOGIN"))
    try:
        MigrationRunner(postgres_engine).upgrade()
        with postgres_engine.connect() as connection:
            privileges = {
                privilege: connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.audit_events', :privilege)"
                    ),
                    {"privilege": privilege},
                ).scalar_one()
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            }
        assert privileges == {
            "SELECT": True,
            "INSERT": True,
            "UPDATE": False,
            "DELETE": False,
            "TRUNCATE": False,
        }
        with postgres_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.sessions', 'DELETE')"
                    )
                ).scalar_one()
                is False
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.dispatch_assignments', 'UPDATE')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.dispatch_idempotency_records', 'UPDATE')"
                )
            ).scalar_one()
            assert connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.dispatch_outbox', 'UPDATE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.rate_limit_buckets', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.support_case_events', 'INSERT')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.support_case_events', 'UPDATE')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.support_cases', 'DELETE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.permissions', 'INSERT')"
                    )
                ).scalar_one()
                is False
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.identity_role_assignments', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.identity_role_assignments', 'DELETE')"
                    )
                ).scalar_one()
                is False
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.identities', 'DELETE')"
                    )
                ).scalar_one()
                is False
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.token_families', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text("DROP OWNED BY ayo_runtime"))
            connection.execute(text("DROP ROLE ayo_runtime"))


def test_repeated_upgrade_preserves_data(postgres_engine, empty_database) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ayo.rides "
                "(public_ride_id, rider_name, pickup, destination, ride_type, "
                "status, driver_queue) VALUES "
                "('migration-proof', 'Rider', 'A', 'B', 'standard', 'requested', "
                "CAST('[]' AS jsonb))"
            )
        )

    runner.upgrade()

    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM ayo.rides WHERE public_ride_id='migration-proof'"
                )
            ).scalar_one()
            == 1
        )


def test_migration_lock_has_bounded_wait(postgres_engine, empty_database) -> None:
    with postgres_engine.connect() as lock_connection:
        try:
            lock_connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            lock_connection.commit()
            with pytest.raises(MigrationLockTimeout):
                MigrationRunner(postgres_engine, lock_timeout_seconds=0.2).upgrade()
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            lock_connection.commit()


def test_concurrent_deployments_serialize_safely(
    postgres_engine, empty_database
) -> None:
    def upgrade() -> None:
        MigrationRunner(postgres_engine, lock_timeout_seconds=5).upgrade()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(upgrade) for _ in range(2)]
        for future in futures:
            future.result()

    assert SchemaVersionReadinessChecker(postgres_engine).check().ready


def test_failed_run_releases_lock_and_recovery_succeeds(
    postgres_engine, empty_database, monkeypatch
) -> None:
    from BACKEND.persistence import migrations

    real_upgrade = migrations.command.upgrade

    def fail_upgrade(config, revision):
        raise RuntimeError("simulated reviewed migration failure")

    monkeypatch.setattr(migrations.command, "upgrade", fail_upgrade)
    with pytest.raises(RuntimeError, match="simulated reviewed migration failure"):
        MigrationRunner(postgres_engine).upgrade()

    monkeypatch.setattr(migrations.command, "upgrade", real_upgrade)
    MigrationRunner(postgres_engine, lock_timeout_seconds=1).upgrade()
    assert SchemaVersionReadinessChecker(postgres_engine).check().ready


def test_dispatch_migration_is_reversible_before_activation(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260715_0007")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert not any(name.startswith("dispatch_") for name in tables)


def test_scheduled_dispatch_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0010")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "ride_reservations" not in tables
    assert not any(name.startswith("reservation_") for name in tables)


def test_active_ride_migration_is_reversible(postgres_engine, empty_database) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0012")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "active_rides" not in tables
    assert not any(name.startswith("active_ride_") for name in tables)


def test_driver_trust_migration_is_reversible(postgres_engine, empty_database) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0014")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "driver_onboarding_cases" not in tables
    assert not any(name.startswith("driver_trust_") for name in tables)


def test_canonical_ride_request_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0015")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "canonical_ride_requests" not in tables
    assert not any(name.startswith("ride_request_") for name in tables)


def test_dispatch_handoff_localization_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0016")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "immediate_dispatch_handoffs" not in tables
    assert "localization_preferences" not in tables


def test_active_ride_lifecycle_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    assert {
        "ride_request_id",
        "dispatch_handoff_id",
        "lifecycle_policy_version",
    }.issubset(
        {
            item["name"]
            for item in inspect(postgres_engine).get_columns(
                "active_rides", schema=AYO_SCHEMA
            )
        }
    )
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0017")
    finally:
        config.attributes["connection"].close()
    columns = {
        item["name"]
        for item in inspect(postgres_engine).get_columns(
            "active_rides", schema=AYO_SCHEMA
        )
    }
    assert "ride_request_id" not in columns
    assert "dispatch_handoff_id" not in columns


def test_pricing_foundation_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade()
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0018")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "pricing_policies" not in tables
    assert "fare_estimates" not in tables
