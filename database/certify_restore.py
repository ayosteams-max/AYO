"""Certify a disposable PostgreSQL backup and restore without application logic."""

from __future__ import annotations

import argparse
import os
import re
import subprocess  # nosec B404 - fixed PostgreSQL CLI argv, never a shell
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class CertificationError(RuntimeError):
    """The isolated restore certification could not complete safely."""


def normalize_database_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def restored_database_url(source_url: str, suffix: str = "_restore_cert") -> str:
    parsed = urlsplit(normalize_database_url(source_url))
    source_name = parsed.path.removeprefix("/")
    if (
        not source_name
        or source_name in {"postgres", "template0", "template1"}
        or re.fullmatch(r"[A-Za-z0-9_]+", source_name) is None
    ):
        raise CertificationError("Source must be a named disposable test database")
    return urlunsplit(parsed._replace(path=f"/{source_name}{suffix}"))


def run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)  # nosec B603 - argv only, shell is disabled
    except (OSError, subprocess.CalledProcessError):
        raise CertificationError(
            f"PostgreSQL certification command failed: {command[0]}"
        ) from None


def certify_restore(source_url: str) -> None:
    source = normalize_database_url(source_url)
    target = restored_database_url(source)
    target_name = urlsplit(target).path.removeprefix("/")
    with tempfile.TemporaryDirectory(prefix="ayo-pg-restore-") as temporary:
        archive = Path(temporary) / "ayo.dump"
        run(["pg_dump", "--format=custom", "--file", str(archive), source])
        run(
            [
                "psql",
                "--no-psqlrc",
                "--set",
                "ON_ERROR_STOP=1",
                "--dbname",
                source,
                "--command",
                f'DROP DATABASE IF EXISTS "{target_name}"',
            ]
        )
        try:
            run(
                [
                    "psql",
                    "--no-psqlrc",
                    "--set",
                    "ON_ERROR_STOP=1",
                    "--dbname",
                    source,
                    "--command",
                    f'CREATE DATABASE "{target_name}"',
                ]
            )
            run(["pg_restore", "--exit-on-error", "--dbname", target, str(archive)])
            run(
                [
                    "psql",
                    "--no-psqlrc",
                    "--set",
                    "ON_ERROR_STOP=1",
                    "--dbname",
                    target,
                    "--command",
                    "SELECT version_num FROM public.ayo_schema_version;",
                ]
            )
        finally:
            run(
                [
                    "psql",
                    "--no-psqlrc",
                    "--set",
                    "ON_ERROR_STOP=1",
                    "--dbname",
                    source,
                    "--command",
                    f'DROP DATABASE IF EXISTS "{target_name}"',
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("AYO_TEST_DATABASE_URL"))
    arguments = parser.parse_args()
    if not arguments.database_url:
        raise CertificationError("AYO_TEST_DATABASE_URL is required")
    certify_restore(arguments.database_url)


if __name__ == "__main__":
    main()
