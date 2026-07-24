from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from BACKEND.authorization.registry import PERMISSION_REGISTRY
from BACKEND.engineering.runtime import EngineeringRuntime
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
        connection.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') "
                "THEN CREATE ROLE ayo_runtime NOLOGIN; END IF; END $$"
            )
        )
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
    expected_tables = {
        table.name for table in metadata.tables.values() if table.schema == AYO_SCHEMA
    }
    assert (
        set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
        == expected_tables
    )
    # Retained as review context; parity authority is SQLAlchemy metadata above.
    _historical_inventory = {
        "active_rides",
        "booking_route_evidence",
        "booking_confirmations",
        "pricing_policies",
        "fare_estimates",
        "fare_estimate_acceptances",
        "fare_calculations",
        "pricing_calculation_components",
        "pricing_idempotency",
        "pricing_events",
        "pricing_outbox",
        "payment_intents",
        "payment_attempts",
        "payment_callback_envelopes",
        "payment_idempotency",
        "payment_events",
        "payment_outbox",
        "refund_requests",
        "refund_decisions",
        "refund_authorizations",
        "refund_evidence",
        "refund_events",
        "refund_outbox",
        "refund_idempotency",
        "settlement_batches",
        "settlement_items",
        "reconciliation_records",
        "reconciliation_exceptions",
        "settlement_approvals",
        "settlement_hold_evidence",
        "settlement_external_evidence",
        "settlement_events",
        "settlement_outbox",
        "settlement_idempotency",
        "wallet_accounts",
        "wallet_lineage_entries",
        "wallet_idempotency",
        "wallet_events",
        "wallet_outbox",
        "financial_postings",
        "financial_posting_lines",
        "financial_posting_idempotency",
        "financial_posting_events",
        "financial_posting_outbox",
        "financial_holds",
        "financial_hold_state_history",
        "financial_hold_idempotency",
        "financial_hold_events",
        "financial_hold_outbox",
        "ledger_books",
        "ledger_accounts",
        "ledger_journals",
        "ledger_entries",
        "ledger_idempotency",
        "ledger_events",
        "ledger_outbox",
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
        "worker_capability_sessions",
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
                    not (
                        reflected
                        and type_ == "table"
                        and name in {VERSION_TABLE, "spatial_ref_sys"}
                    )
                ),
            },
        )
        assert compare_metadata(context, metadata) == []
        registered_permissions = set(
            connection.execute(text("SELECT code FROM ayo.permissions")).scalars()
        )
        immutable_triggers = set(
            connection.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgname IN ('trg_mobility_geometry_immutable', "
                    "'trg_mobility_evaluation_immutable') AND NOT tgisinternal"
                )
            ).scalars()
        )
    assert registered_permissions == set(PERMISSION_REGISTRY)
    assert immutable_triggers == {
        "trg_mobility_geometry_immutable",
        "trg_mobility_evaluation_immutable",
    }
    assert extensions_after == extensions_before | {"btree_gist"}


def test_canonical_compatibility_upgrades_from_previous_revision(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0044")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "canonical_subjects" not in before
    assert "identity_accounts" not in before
    assert "legacy_identity_mappings" not in before

    runner.upgrade()

    after = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert {
        "canonical_subjects",
        "identity_accounts",
        "legacy_identity_mappings",
    } <= after
    assert SchemaVersionReadinessChecker(postgres_engine).check().current_revision == (
        "20260723_0051"
    )


def test_identity_security_upgrades_from_certified_account_access_revision(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0046")
    runner.upgrade("20260723_0047")
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert {
        "identity_security_bootstrap",
        "account_recovery_tokens",
        "authentication_origin_windows",
    } <= tables
    assert SchemaVersionReadinessChecker(postgres_engine).check().current_revision == (
        "20260723_0047"
    )


def test_customer_profile_upgrades_from_identity_increment_2(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0047")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "customer_profiles" not in before

    runner.upgrade("20260723_0048")
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert {
        "customer_profiles",
        "customer_household_relationships",
        "customer_emergency_contacts",
    } <= tables
    assert SchemaVersionReadinessChecker(postgres_engine).check().current_revision == (
        "20260723_0048"
    )


def test_r1_passenger_mobility_upgrades_from_customer_household(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0048")
    before_foreign_keys = {
        row["name"]
        for row in inspect(postgres_engine).get_foreign_keys(
            "canonical_ride_requests", schema=AYO_SCHEMA
        )
    }
    assert "fk_ride_requests_requester_subject" not in before_foreign_keys

    runner.upgrade("20260723_0049")
    columns = {
        row["name"]: row
        for row in inspect(postgres_engine).get_columns(
            "canonical_ride_requests", schema=AYO_SCHEMA
        )
    }
    assert {
        "mobility_model_version",
        "requester_subject_id",
        "passenger_subject_id",
        "pickup_reference",
        "destination_reference",
        "stop_references",
        "schedule_intent",
        "scheduled_for",
        "passenger_count",
        "ride_preferences",
    } <= columns.keys()
    assert columns["rider_identity_id"]["nullable"]
    assert columns["pickup_id"]["nullable"]
    foreign_keys = {
        row["name"]
        for row in inspect(postgres_engine).get_foreign_keys(
            "canonical_ride_requests", schema=AYO_SCHEMA
        )
    }
    assert {
        "fk_ride_requests_requester_subject",
        "fk_ride_requests_passenger_subject",
    } <= foreign_keys
    assert (
        SchemaVersionReadinessChecker(postgres_engine).check().current_revision
        == "20260723_0049"
    )


def test_account_access_upgrades_from_certified_compatibility_revision(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0045")
    runner.upgrade("20260723_0046")
    with postgres_engine.connect() as connection:
        columns = {
            row["name"]
            for row in inspect(connection).get_columns(
                "identity_accounts", schema=AYO_SCHEMA
            )
        }
        tables = set(inspect(connection).get_table_names(schema=AYO_SCHEMA))
    assert {"failed_attempt_count", "last_failed_at"} <= columns
    assert {
        "account_password_credentials",
        "account_sessions",
        "account_role_assignments",
    } <= tables
    assert SchemaVersionReadinessChecker(postgres_engine).check().current_revision == (
        "20260723_0046"
    )


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
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.persistence_domain_events', 'UPDATE')"
                )
            ).scalar_one()
            assert connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.persistence_outbox', 'UPDATE')"
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
            for immutable_table in (
                "settlement_approvals",
                "settlement_hold_evidence",
                "settlement_external_evidence",
            ):
                assert connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        f"'ayo_runtime', 'ayo.{immutable_table}', 'INSERT')"
                    )
                ).scalar_one()
                assert not connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        f"'ayo_runtime', 'ayo.{immutable_table}', 'UPDATE')"
                    )
                ).scalar_one()
                assert not connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        f"'ayo_runtime', 'ayo.{immutable_table}', 'DELETE')"
                    )
                ).scalar_one()
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
            for table_name, update_allowed in (
                ("canonical_subjects", False),
                ("identity_accounts", True),
                ("legacy_identity_mappings", True),
            ):
                assert connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        f"'ayo_runtime', 'ayo.{table_name}', 'SELECT')"
                    )
                ).scalar_one()
                assert connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        f"'ayo_runtime', 'ayo.{table_name}', 'INSERT')"
                    )
                ).scalar_one()
                assert (
                    connection.execute(
                        text(
                            "SELECT has_table_privilege("
                            f"'ayo_runtime', 'ayo.{table_name}', 'UPDATE')"
                        )
                    ).scalar_one()
                    is update_allowed
                )
                assert not connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        f"'ayo_runtime', 'ayo.{table_name}', 'DELETE')"
                    )
                ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.token_families', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.payment_attempts', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.payment_outbox', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.refund_requests', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.refund_decisions', 'INSERT')"
                    )
                ).scalar_one()
                is True
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.refund_requests', 'DELETE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.settlement_batches', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.reconciliation_records', 'INSERT')"
                    )
                ).scalar_one()
                is True
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.settlement_batches', 'DELETE')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.payment_intents', 'DELETE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.wallet_accounts', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.wallet_lineage_entries', 'INSERT')"
                    )
                ).scalar_one()
                is True
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.wallet_lineage_entries', 'DELETE')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.wallet_accounts', 'DELETE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.financial_postings', 'INSERT')"
                    )
                ).scalar_one()
                is True
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.financial_postings', 'UPDATE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.financial_posting_outbox', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.financial_posting_lines', 'DELETE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.financial_holds', 'INSERT')"
                    )
                ).scalar_one()
                is True
            )
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.financial_holds', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.financial_hold_state_history', 'UPDATE')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege("
                    "'ayo_runtime', 'ayo.financial_hold_state_history', 'DELETE')"
                )
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'ayo_runtime', 'ayo.financial_hold_outbox', 'UPDATE')"
                    )
                ).scalar_one()
                is True
            )
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text("DROP OWNED BY ayo_runtime"))
            connection.execute(text("DROP ROLE ayo_runtime"))


def test_dispatch_evidence_migration_supports_preexisting_0017_schema(
    postgres_engine, empty_database
) -> None:
    MigrationRunner(postgres_engine).upgrade("20260720_0029")
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE ayo.immediate_dispatch_candidate_sets "
                "DROP COLUMN IF EXISTS decision_evidence"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE ayo.immediate_dispatch_offers "
                "DROP COLUMN IF EXISTS route_evidence_id, "
                "DROP COLUMN IF EXISTS decision_reason_codes"
            )
        )
    MigrationRunner(postgres_engine).upgrade("head")
    inspector = inspect(postgres_engine)
    assert "decision_evidence" in {
        item["name"]
        for item in inspector.get_columns(
            "immediate_dispatch_candidate_sets", schema=AYO_SCHEMA
        )
    }
    assert {"route_evidence_id", "decision_reason_codes"} <= {
        item["name"]
        for item in inspector.get_columns(
            "immediate_dispatch_offers", schema=AYO_SCHEMA
        )
    }


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
        MigrationRunner(postgres_engine, lock_timeout_seconds=30).upgrade()

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


def test_engineering_runtime_is_ready_after_migration_and_restart(
    postgres_engine, empty_database
) -> None:
    MigrationRunner(postgres_engine).upgrade()

    first_process = EngineeringRuntime(postgres_engine, persistence_required=True)
    first_process.start()
    assert first_process.readiness().ready
    first_process.close()
    assert not first_process.live

    restarted_process = EngineeringRuntime(postgres_engine, persistence_required=True)
    restarted_process.start()
    assert restarted_process.readiness().ready
    restarted_process.close()


def test_dispatch_migration_is_reversible_before_activation(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260716_0008")
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
    runner.upgrade("20260716_0011")
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
    runner.upgrade("20260716_0013")
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
    runner.upgrade("20260716_0015")
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
    runner.upgrade("20260716_0016")
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
    runner.upgrade("20260716_0017")
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
    runner.upgrade("20260716_0018")
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
    runner.upgrade("20260716_0019")
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


def test_ledger_foundation_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260717_0020")
    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260716_0019")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "ledger_books" not in tables
    assert "ledger_journals" not in tables


def test_payment_foundation_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260717_0021")
    with postgres_engine.connect() as connection:
        indexes = {
            item["name"]
            for item in inspect(connection).get_indexes(
                "payment_attempts", schema=AYO_SCHEMA
            )
        }
        assert "uq_payment_attempt_single_active_per_intent" in indexes

    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260717_0020")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "payment_intents" not in tables
    assert "payment_attempts" not in tables


def test_wallet_foundation_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260717_0024")
    with postgres_engine.connect() as connection:
        indexes = {
            item["name"]
            for item in inspect(connection).get_indexes(
                "wallet_lineage_entries", schema=AYO_SCHEMA
            )
        }
        assert "ix_wallet_lineage_account_time" in indexes

    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260717_0023")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "wallet_accounts" not in tables
    assert "wallet_lineage_entries" not in tables


def test_financial_posting_engine_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260717_0025")
    with postgres_engine.connect() as connection:
        indexes = {
            item["name"]
            for item in inspect(connection).get_indexes(
                "financial_posting_lines", schema=AYO_SCHEMA
            )
        }
        assert "ix_financial_posting_lines_posting" in indexes

    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260717_0024")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "financial_postings" not in tables
    assert "financial_posting_lines" not in tables


def test_financial_hold_engine_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260717_0026")
    with postgres_engine.connect() as connection:
        indexes = {
            item["name"]
            for item in inspect(connection).get_indexes(
                "financial_hold_state_history", schema=AYO_SCHEMA
            )
        }
        assert "ix_financial_hold_history_hold_time" in indexes

    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260717_0025")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "financial_holds" not in tables
    assert "financial_hold_state_history" not in tables


def test_settlement_reconciliation_evolution_migration_is_reversible(
    postgres_engine, empty_database
) -> None:
    MigrationRunner(postgres_engine).upgrade("20260718_0027")
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "settlement_approvals" in tables
    assert "settlement_hold_evidence" in tables
    assert "settlement_external_evidence" in tables

    from alembic import command

    config = alembic_config()
    config.attributes["connection"] = postgres_engine.connect()
    try:
        command.downgrade(config, "20260717_0026")
    finally:
        config.attributes["connection"].close()
    tables = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))
    assert "settlement_approvals" not in tables
    assert "settlement_hold_evidence" not in tables
    assert "settlement_external_evidence" not in tables


def test_request_access_increment_migrates_additively_from_service_area(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0050")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    runner.upgrade("20260723_0051")
    after = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    assert before <= after
    assert {
        "request_access_source_adapters",
        "request_access_channel_capabilities",
        "request_access_continuity_references",
        "request_access_interaction_provenance",
    } <= after
    with postgres_engine.connect() as connection:
        permissions = set(
            connection.execute(
                text(
                    "SELECT code FROM ayo.permissions "
                    "WHERE code LIKE 'access.provenance.%'"
                )
            ).scalars()
        )
    assert permissions == {
        "access.provenance.manage",
        "access.provenance.record",
        "access.provenance.support",
    }


def test_p2_eat_increment_one_migrates_additively_from_request_access(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0051")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    runner.upgrade("20260723_0052")
    inspector = inspect(postgres_engine)
    after = set(inspector.get_table_names(schema=AYO_SCHEMA))

    assert before <= after
    assert {
        "catalogue_modifier_options",
        "p2_eat_availability_policies",
        "p2_eat_availability_policy_history",
        "p2_eat_availability_evaluations",
        "p2_eat_availability_idempotency",
        "p2_eat_availability_outbox",
    } <= after
    order_columns = {
        value["name"]
        for value in inspector.get_columns("commerce_orders", schema=AYO_SCHEMA)
    }
    line_columns = {
        value["name"]
        for value in inspector.get_columns("commerce_order_lines", schema=AYO_SCHEMA)
    }
    assert {
        "availability_evaluation_id",
        "composition_hash",
        "access_interaction_id",
    } <= order_columns
    assert {"modifier_selections", "customer_instructions"} <= line_columns
    with postgres_engine.connect() as connection:
        permission = connection.execute(
            text(
                "SELECT code FROM ayo.permissions "
                "WHERE code = 'eat.availability.manage'"
            )
        ).scalar_one()
    assert permission == "eat.availability.manage"


def test_p2_eat_increment_two_migrates_additively_from_increment_one(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0052")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    runner.upgrade("20260723_0053")
    after = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    assert before <= after
    assert {
        "merchant_staff_decision_authorities",
        "merchant_decision_cases",
        "merchant_decision_evidence",
        "merchant_decision_idempotency",
        "merchant_decision_outbox",
    } <= after
    with postgres_engine.connect() as connection:
        permissions = set(
            connection.execute(
                text(
                    "SELECT code FROM ayo.permissions WHERE code IN "
                    "('merchant_orders.admit_decision',"
                    "'merchant_orders.expire_decisions')"
                )
            ).scalars()
        )
    assert permissions == {
        "merchant_orders.admit_decision",
        "merchant_orders.expire_decisions",
    }


def test_p2_eat_increment_three_migrates_additively_from_increment_two(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0053")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    runner.upgrade("20260723_0054")
    after = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    assert before <= after
    assert {
        "preparation_staff_authorities",
        "preparation_cases",
        "preparation_evidence",
        "preparation_idempotency",
        "preparation_outbox",
    } <= after
    with postgres_engine.connect() as connection:
        permissions = set(
            connection.execute(
                text(
                    "SELECT code FROM ayo.permissions WHERE code IN "
                    "('merchant_preparation.admit',"
                    "'merchant_preparation.observe_overdue')"
                )
            ).scalars()
        )
    assert permissions == {
        "merchant_preparation.admit",
        "merchant_preparation.observe_overdue",
    }


def test_courier_dispatch_increment_one_migrates_additively(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0054")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    runner.upgrade("20260723_0055")
    after = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    assert before <= after
    assert {
        "courier_dispatch_offers",
        "courier_dispatch_assignments",
        "courier_dispatch_evidence",
    } <= after
    with postgres_engine.connect() as connection:
        permissions = set(
            connection.execute(
                text(
                    "SELECT code FROM ayo.permissions WHERE code IN "
                    "('courier_dispatch.manage','courier_dispatch.admit')"
                )
            ).scalars()
        )
        state_constraint = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = "
                "'ck_commerce_courier_dispatch_requests_courier_dispatch_state_valid'"
            )
        ).scalar_one()
    assert permissions == {"courier_dispatch.manage", "courier_dispatch.admit"}
    assert "dispatch_cancelled" in state_constraint
    assert "dispatch_unfulfilled" in state_constraint


def test_courier_pickup_increment_one_migrates_additively(
    postgres_engine, empty_database
) -> None:
    runner = MigrationRunner(postgres_engine)
    runner.upgrade("20260723_0055")
    before = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    runner.upgrade("20260724_0056")
    after = set(inspect(postgres_engine).get_table_names(schema=AYO_SCHEMA))

    assert before <= after
    assert "commerce_courier_pickup_evidence" in after
    columns = {
        column["name"]
        for column in inspect(postgres_engine).get_columns(
            "commerce_courier_pickups", schema=AYO_SCHEMA
        )
    }
    assert {
        "assignment_id",
        "assignment_version",
        "attempt_number",
        "policy_code",
        "policy_version",
        "terminal_reason",
        "custody_accepted_at",
    } <= columns
    with postgres_engine.connect() as connection:
        permissions = set(
            connection.execute(
                text(
                    "SELECT code FROM ayo.permissions WHERE code LIKE "
                    "'courier_pickup.%' AND code LIKE '%.%assigned' "
                    "OR code IN ('courier_pickup.correct_own_merchant',"
                    "'courier_pickup.close_own_merchant')"
                )
            ).scalars()
        )
    assert {
        "courier_pickup.correct_assigned",
        "courier_pickup.close_assigned",
        "courier_pickup.correct_own_merchant",
        "courier_pickup.close_own_merchant",
    } <= permissions
