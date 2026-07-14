from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from BACKEND.persistence.migrations import (
    MIGRATION_LOCK_ID,
    MigrationLockTimeout,
    MigrationRunner,
    SchemaVersionReadinessChecker,
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
        "legacy_wallets",
        "rides",
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
    assert extensions_after == extensions_before


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
        lock_connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
        )
        lock_connection.commit()
        with pytest.raises(MigrationLockTimeout):
            MigrationRunner(postgres_engine, lock_timeout_seconds=0.2).upgrade()


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
