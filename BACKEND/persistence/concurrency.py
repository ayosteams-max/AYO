from collections.abc import Mapping
from typing import Any

from sqlalchemy import ColumnElement, Connection, Table, update

from BACKEND.persistence.errors import OptimisticConcurrencyError


def compare_and_swap(
    connection: Connection,
    *,
    table: Table,
    identity: ColumnElement[bool],
    expected_version: int,
    values: Mapping[str, Any],
    version_column: str = "version",
) -> int:
    """Apply a bounded update only when the authoritative version still matches."""

    if expected_version < 1:
        raise ValueError("Expected version must be positive")
    try:
        version = table.c[version_column]
    except KeyError as error:
        raise ValueError(
            "Versioned table does not expose the configured column"
        ) from error
    if version_column in values:
        raise ValueError("Callers cannot set the version directly")
    next_version = connection.execute(
        update(table)
        .where(identity, version == expected_version)
        .values(**dict(values), **{version_column: version + 1})
        .returning(version)
    ).scalar_one_or_none()
    if next_version is None:
        raise OptimisticConcurrencyError("Stored record changed before the update.")
    return int(next_version)
