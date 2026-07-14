import json
import logging

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine

from BACKEND.persistence.config import DatabaseSettings
from BACKEND.persistence.engine import create_postgres_engine
from BACKEND.persistence.errors import RepositoryConfigurationError
from BACKEND.persistence.health import DatabaseHealthChecker
from BACKEND.persistence.logging import StructuredJsonFormatter, database_event
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


def test_database_settings_hide_credentials_and_require_explicit_url():
    settings = DatabaseSettings(
        url=SecretStr("postgresql+psycopg://user:secret@db/ayo")
    )

    assert "secret" not in repr(settings)
    assert settings.require_url().endswith("@db/ayo")

    with pytest.raises(RuntimeError, match="AYO_DATABASE_URL"):
        DatabaseSettings(url=None).require_url()


def test_structured_database_log_contains_only_supplied_safe_fields():
    logger = logging.getLogger("test.persistence.logging")
    record = None

    class Capture(logging.Handler):
        def emit(self, emitted: logging.LogRecord) -> None:
            nonlocal record
            record = emitted

    handler = Capture()
    handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        database_event(logger, "ride.get", "found", 1.2345, pool_size=5)
    finally:
        logger.removeHandler(handler)

    assert record is not None
    payload = json.loads(handler.format(record))
    assert payload["event"] == "ride.get"
    assert payload["duration_ms"] == 1.234
    assert "secret" not in payload


def test_generic_unit_of_work_rolls_back_and_validates_composition():
    engine = create_engine("sqlite://")
    try:
        unit_of_work = SqlAlchemyUnitOfWork(engine, {})

        with unit_of_work, pytest.raises(RepositoryConfigurationError):
            unit_of_work.repository("missing", object)

        with pytest.raises(RuntimeError, match="not been entered"):
            _ = unit_of_work.connection
    finally:
        engine.dispose()


def test_postgres_engine_is_bounded_and_does_not_connect_during_construction():
    settings = DatabaseSettings(
        url=SecretStr("postgresql+psycopg://user:secret@127.0.0.1:1/ayo"),
        ssl_mode="disable",
        pool_size=2,
        max_overflow=1,
        pool_timeout_seconds=0.1,
    )
    engine = create_postgres_engine(settings)
    try:
        assert engine.pool.size() == 2
        assert "secret" not in repr(engine.url)
        assert "***" in repr(engine.url)
    finally:
        engine.dispose()


def test_database_health_returns_safe_error_category():
    settings = DatabaseSettings(
        url=SecretStr("postgresql+psycopg://user:secret@127.0.0.1:1/ayo"),
        ssl_mode="disable",
        connect_timeout_seconds=1,
        pool_timeout_seconds=1,
    )
    engine = create_postgres_engine(settings)
    try:
        result = DatabaseHealthChecker(engine).check()
        assert not result.ready
        assert result.error_category
        assert "secret" not in result.error_category
    finally:
        engine.dispose()
