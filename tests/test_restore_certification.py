import subprocess
from unittest.mock import patch

import pytest

from database.certify_restore import (
    CertificationError,
    certify_restore,
    normalize_database_url,
    restored_database_url,
    run,
)


def test_normalizes_sqlalchemy_postgresql_url() -> None:
    assert (
        normalize_database_url("postgresql+psycopg://user:secret@db:5432/ayo_test")
        == "postgresql://user:secret@db:5432/ayo_test"
    )


def test_restore_target_is_isolated_and_rejects_system_database() -> None:
    assert restored_database_url("postgresql://u:p@db/ayo_test").endswith(
        "/ayo_test_restore_cert"
    )
    with pytest.raises(CertificationError):
        restored_database_url("postgresql://u:p@db/postgres")


@patch("database.certify_restore.tempfile.TemporaryDirectory")
@patch("database.certify_restore.run")
def test_restore_certification_cleans_target_after_validation(
    run_mock, temporary_mock
) -> None:
    temporary_mock.return_value.__enter__.return_value = "C:/temp/cert"
    certify_restore("postgresql+psycopg://u:p@db/ayo_test")
    target = "postgresql://u:p@db/ayo_test_restore_cert"
    assert run_mock.call_args_list[0].args[0][0] == "pg_dump"
    assert any(item.args[0][0] == "pg_restore" for item in run_mock.call_args_list)
    assert any(item.args[0][0] == "psql" for item in run_mock.call_args_list)
    assert target in str(run_mock.call_args_list)
    assert 'DROP DATABASE IF EXISTS "ayo_test_restore_cert"' in str(
        run_mock.call_args_list[-1]
    )


@patch("database.certify_restore.subprocess.run")
def test_failed_command_does_not_expose_arguments(run_mock) -> None:
    run_mock.side_effect = subprocess.CalledProcessError(1, ["psql", "secret-url"])
    with pytest.raises(CertificationError) as captured:
        run(["psql", "secret-url"])
    assert "psql" in str(captured.value)
    assert "secret-url" not in str(captured.value)
