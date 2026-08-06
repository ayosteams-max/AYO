import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic.script import ScriptDirectory

from BACKEND.persistence.migrations import (
    MigrationLockTimeout,
    MigrationRunner,
    SchemaVersionReadinessChecker,
    alembic_config,
    expected_schema_revision,
)


def test_migration_history_has_one_expected_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == ["20260806_0058"]
    assert expected_schema_revision() == "20260806_0058"


def test_mobile_context_migration_changes_only_the_courier_lookup_index() -> None:
    path = (
        Path(__file__).parents[1]
        / "database/migrations/versions/20260806_0058_mobile_actor_context_index.py"
    )
    spec = importlib.util.spec_from_file_location("mobile_actor_context_index", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op.create_index = MagicMock()
    module.op.drop_index = MagicMock()

    module.upgrade()
    module.op.create_index.assert_called_once()
    call = module.op.create_index.call_args
    assert call.args[:2] == (
        "ix_courier_pickup_current_courier",
        "commerce_courier_pickups",
    )
    assert call.kwargs["unique"] is False
    assert call.kwargs["schema"] == "ayo"
    assert "assigned_courier_identity_id" in call.args[2]
    assert "postgresql_where" in call.kwargs

    module.downgrade()
    module.op.drop_index.assert_called_once_with(
        "ix_courier_pickup_current_courier",
        table_name="commerce_courier_pickups",
        schema="ayo",
    )


def test_destructive_initial_downgrade_is_prohibited() -> None:
    path = (
        Path(__file__).parents[1]
        / "database/migrations/versions/20260715_0001_initial_ayo_schema.py"
    )
    spec = importlib.util.spec_from_file_location("initial_ayo_schema", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(RuntimeError, match="Destructive downgrade is prohibited"):
        module.downgrade()


def test_migration_lock_timeout_is_safe_and_bounded() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = False

    with pytest.raises(MigrationLockTimeout):
        MigrationRunner(engine, lock_timeout_seconds=0.001).upgrade()

    connection.rollback.assert_called_once()


def test_schema_readiness_returns_safe_unavailable_result() -> None:
    engine = MagicMock()
    engine.connect.return_value.__enter__.side_effect = RuntimeError(
        "secret connection detail"
    )

    result = SchemaVersionReadinessChecker(engine).check()

    assert not result.ready
    assert result.current_revision is None
    assert result.reason == "schema_check_unavailable"
    assert "secret" not in result.reason
