import os

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, text

from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.config import DatabaseSettings
from BACKEND.persistence.engine import create_postgres_engine
from BACKEND.persistence.tables import (
    AYO_SCHEMA,
    audit_events,
    legacy_wallets,
    metadata,
    rides,
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
        connection.execute(delete(audit_events))
        connection.execute(delete(legacy_wallets))
        connection.execute(delete(rides))


@pytest.fixture
def postgres_composition(postgres_engine):
    return PostgresRepositoryComposition(postgres_engine)
