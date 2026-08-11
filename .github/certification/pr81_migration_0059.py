"""Temporary, sanitized PostgreSQL certification for PR #81 migration 0059."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine

APPROVED_SHA = "c63d3ed8748be381dead9f6e0ff6eadcb367d755"
APPROVED_TREE = "b1c19771487f406a5bcbce0f584b04f1d2a1e706"
REVISION_0058 = "20260806_0058"
REVISION_0059 = "20260811_0059"
DATABASES = ("pr81_fresh", "pr81_genuine_0058")
SCHEMA = "ayo"
VERSION_TABLE = "ayo_schema_version"
MIGRATION_LOCK_ID = 18_412_138_359_126_354
EVIDENCE_TABLES = (
    "booking_confirmations",
    "immediate_dispatch_handoffs",
    "post_trip_records",
    "trip_cash_collection_evidence",
    "cash_accounting_policies",
    "trip_cash_accounting_records",
    "cash_reconciliation_evidence",
)
NEW_TABLES = {
    "trip_cash_collection_evidence",
    "cash_accounting_policies",
    "trip_cash_accounting_records",
    "cash_reconciliation_evidence",
}
EXPECTED_COLUMNS = {
    "booking_confirmations": {
        "fare_estimate_id",
        "estimate_acceptance_id",
        "pricing_lineage_hash",
    },
    "immediate_dispatch_handoffs": {
        "fare_estimate_id",
        "estimate_acceptance_id",
        "pricing_policy_id",
        "pricing_policy_version",
        "pricing_lineage_hash",
    },
    "post_trip_records": {"cash_evidence_state"},
}
EXPECTED_CONSTRAINTS = {
    "booking_confirmations": {
        "fk_booking_confirmation_fare_estimate",
        "fk_booking_confirmation_estimate_acceptance",
        "uq_booking_confirmation_fare_estimate",
        "uq_booking_confirmation_estimate_acceptance",
    },
    "immediate_dispatch_handoffs": {
        "fk_handoff_fare_estimate",
        "fk_handoff_estimate_acceptance",
        "fk_handoff_pricing_policy",
        "ck_immediate_dispatch_handoffs_handoff_pricing_lineage_complete",
    },
    "trip_cash_accounting_records": {
        "ck_trip_cash_accounting_records_cash_accounting_record__1da1",
    },
}
SYNTHETIC_POLICY_ID = UUID("81000000-0000-4000-8000-000000000058")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def connection_kwargs(database: str) -> dict[str, Any]:
    return {
        "host": os.environ["PGHOST"],
        "port": int(os.environ["PGPORT"]),
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "dbname": database,
    }


def engine(database: str) -> Engine:
    return create_engine(
        URL.create(
            "postgresql+psycopg",
            username=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            host=os.environ["PGHOST"],
            port=int(os.environ["PGPORT"]),
            database=database,
        )
    )


def recreate_database(database: str) -> None:
    with psycopg.connect(
        **connection_kwargs("postgres"), autocommit=True
    ) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid<>pg_backend_pid()",
            (database,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
        connection.execute(f'CREATE DATABASE "{database}"')
    with psycopg.connect(**connection_kwargs(database), autocommit=True) as connection:
        connection.execute("CREATE EXTENSION postgis")
        if (
            connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime'"
            ).fetchone()
            is None
        ):
            connection.execute("CREATE ROLE ayo_runtime NOLOGIN")


def cleanup() -> None:
    with psycopg.connect(
        **connection_kwargs("postgres"), autocommit=True
    ) as connection:
        for database in DATABASES:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (database,),
            )
            connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
    print("Disposable certification databases removed: 2")


def prepare_predecessor_database() -> None:
    recreate_database(DATABASES[1])
    print("Disposable genuine-predecessor database prepared")


def migrate(db_engine: Engine, revision: str, *, downgrade: bool = False) -> None:
    from BACKEND.persistence.migrations import alembic_config

    with db_engine.connect() as connection:
        locked = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            ).scalar_one()
        )
        connection.commit()
        if not locked:
            raise RuntimeError("certification migration lock unavailable")
        try:
            config = alembic_config()
            config.attributes["connection"] = connection
            operation = command.downgrade if downgrade else command.upgrade
            operation(config, revision)
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            connection.commit()


def revision(db_engine: Engine) -> str:
    with db_engine.connect() as connection:
        return str(
            connection.execute(
                text('SELECT version_num FROM public."ayo_schema_version"')
            ).scalar_one()
        )


def inventory(db_engine: Engine) -> dict[str, Any]:
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names(schema=SCHEMA))
    result: dict[str, Any] = {"tables": sorted(tables), "objects": {}}
    for table_name in EVIDENCE_TABLES:
        if table_name not in tables:
            continue
        columns: list[dict[str, Any]] = [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": bool(column["nullable"]),
            }
            for column in inspector.get_columns(table_name, schema=SCHEMA)
        ]
        constraints: list[dict[str, Any]] = []
        for foreign_key in inspector.get_foreign_keys(table_name, schema=SCHEMA):
            constraints.append(
                {
                    "kind": "foreign_key",
                    "name": foreign_key["name"],
                    "columns": foreign_key["constrained_columns"],
                    "target_schema": foreign_key["referred_schema"],
                    "target_table": foreign_key["referred_table"],
                    "target_columns": foreign_key["referred_columns"],
                }
            )
        for unique in inspector.get_unique_constraints(table_name, schema=SCHEMA):
            constraints.append(
                {
                    "kind": "unique",
                    "name": unique["name"],
                    "columns": unique["column_names"],
                }
            )
        for check in inspector.get_check_constraints(table_name, schema=SCHEMA):
            constraints.append(
                {
                    "kind": "check",
                    "name": check["name"],
                    "sql": "".join(str(check["sqltext"]).lower().split()),
                }
            )
        indexes: list[dict[str, Any]] = [
            {
                "name": item["name"],
                "columns": item["column_names"],
                "unique": bool(item["unique"]),
            }
            for item in inspector.get_indexes(table_name, schema=SCHEMA)
        ]
        result["objects"][table_name] = {
            "columns": sorted(columns, key=lambda item: item["name"]),
            "constraints": sorted(
                constraints, key=lambda item: (str(item["name"]), item["kind"])
            ),
            "indexes": sorted(indexes, key=lambda item: str(item["name"])),
        }
    return result


def validate_0059(db_engine: Engine) -> dict[str, Any]:
    from BACKEND.persistence.tables import metadata

    state = inventory(db_engine)
    expected_tables = {
        table.name for table in metadata.tables.values() if table.schema == SCHEMA
    }
    if set(state["tables"]) != expected_tables:
        raise AssertionError("0059 table inventory differs from canonical metadata")
    if not set(state["tables"]) >= NEW_TABLES:
        raise AssertionError("0059 financial evidence tables are incomplete")
    for table_name, expected in EXPECTED_COLUMNS.items():
        actual = {item["name"] for item in state["objects"][table_name]["columns"]}
        if not expected <= actual:
            raise AssertionError(f"0059 columns missing from {table_name}")
    for table_name, expected_names in EXPECTED_CONSTRAINTS.items():
        names = [
            constraint["name"]
            for constraint in state["objects"][table_name]["constraints"]
            if constraint["name"] is not None
        ]
        for constraint_name in expected_names:
            if names.count(constraint_name) != 1:
                raise AssertionError(
                    f"constraint {SCHEMA}.{table_name}.{constraint_name} "
                    f"does not exist exactly once; observed={sorted(names)!r}"
                )
        if len(names) != len(set(names)):
            raise AssertionError(f"duplicate named constraints found on {table_name}")
    for value in state["objects"].values():
        index_names = [item["name"] for item in value["indexes"]]
        if len(index_names) != len(set(index_names)):
            raise AssertionError("duplicate index found in 0059 inventory")
    # The exact full-table comparison above is authoritative, but evidence retains
    # only the bounded 0059-relevant inventory to avoid unrelated sensitive names.
    state["tables"] = sorted(set(state["tables"]) & set(EVIDENCE_TABLES))
    return state


def validate_0058(db_engine: Engine) -> None:
    state = inventory(db_engine)
    if NEW_TABLES & set(state["tables"]):
        raise AssertionError("0059-owned tables survived downgrade")
    for table_name, expected in EXPECTED_COLUMNS.items():
        if table_name not in state["objects"]:
            continue
        actual = {item["name"] for item in state["objects"][table_name]["columns"]}
        if expected & actual:
            raise AssertionError(f"0059-owned columns survived on {table_name}")


def seed_predecessor_data(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ayo.pricing_policies "
                "(policy_id,policy_version,service_zone_id,service_type,currency,"
                "base_fare_minor,distance_rate_per_km_minor,time_rate_per_minute_minor,"
                "minimum_fare_minor,commission_basis_points,tax_placeholder_basis_points,"
                "rounding_increment_minor,effective_from,status,made_by_identity_id,created_at) "
                "VALUES (:id,'pr81-predecessor-v0058',:zone,'immediate_standard','ETB',"
                "100,10,5,100,0,0,1,:now,'draft',:maker,:now)"
            ),
            {
                "id": SYNTHETIC_POLICY_ID,
                "zone": UUID("81000000-0000-4000-8000-000000000059"),
                "maker": UUID("81000000-0000-4000-8000-000000000060"),
                "now": datetime(2026, 8, 11, tzinfo=UTC),
            },
        )


def predecessor_data_exists(db_engine: Engine) -> bool:
    with db_engine.connect() as connection:
        return bool(
            connection.execute(
                text("SELECT count(*)=1 FROM ayo.pricing_policies WHERE policy_id=:id"),
                {"id": SYNTHETIC_POLICY_ID},
            ).scalar_one()
        )


def versions() -> tuple[str, str]:
    with psycopg.connect(**connection_kwargs("postgres")) as connection:
        server_row = connection.execute("SHOW server_version").fetchone()
        postgis_row = connection.execute(
            "SELECT default_version FROM pg_available_extensions WHERE name='postgis'"
        ).fetchone()
        if server_row is None or postgis_row is None:
            raise RuntimeError("database version evidence unavailable")
        server = str(server_row[0])
        postgis = str(postgis_row[0])
    if not server.startswith("17.") or not postgis.startswith("3.5"):
        raise AssertionError("certification requires PostgreSQL 17 and PostGIS 3.5")
    return server, postgis


def certify(evidence_path: Path) -> None:
    evidence: dict[str, Any] = {
        "schema_version": "pr81-migration-0059-certification-v1",
        "candidate_sha": APPROVED_SHA,
        "candidate_tree": APPROVED_TREE,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "unknown"),
        "started_at": utc_now(),
        "status": "FAIL",
        "candidate_defect": "UNKNOWN",
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        server, postgis = versions()
        evidence["postgresql_version"] = server
        evidence["postgis_version"] = postgis
        recreate_database(DATABASES[0])
        fresh = engine(DATABASES[0])
        genuine = engine(DATABASES[1])
        migrate(fresh, "head")
        if revision(fresh) != REVISION_0059:
            raise AssertionError("fresh database did not reach exact 0059")
        fresh_inventory = validate_0059(fresh)
        if revision(genuine) != REVISION_0058:
            raise AssertionError("genuine predecessor did not stop at exact 0058")
        validate_0058(genuine)
        seed_predecessor_data(genuine)
        migrate(genuine, REVISION_0059)
        if revision(genuine) != REVISION_0059 or not predecessor_data_exists(genuine):
            raise AssertionError("0058 to 0059 did not preserve predecessor evidence")
        first_inventory = validate_0059(genuine)
        migrate(genuine, REVISION_0058, downgrade=True)
        if revision(genuine) != REVISION_0058 or not predecessor_data_exists(genuine):
            raise AssertionError(
                "0059 downgrade did not restore 0058 with preserved data"
            )
        validate_0058(genuine)
        migrate(genuine, REVISION_0059)
        if revision(genuine) != REVISION_0059 or not predecessor_data_exists(genuine):
            raise AssertionError(
                "0059 re-upgrade did not preserve predecessor evidence"
            )
        second_inventory = validate_0059(genuine)
        if first_inventory != second_inventory:
            raise AssertionError("0059 schema diverged after downgrade and re-upgrade")
        evidence.update(
            {
                "migration_paths": {
                    "fresh_to_0059": "PASS",
                    "0058_to_0059": "PASS",
                    "0059_to_0058": "PASS",
                    "0058_to_0059_reupgrade": "PASS",
                    "predecessor_data_preservation": "PASS",
                },
                "fresh_schema_inventory": fresh_inventory,
                "roundtrip_schema_inventory": second_inventory,
                "schema_equality": "PASS",
                "constraint_index_equality": "PASS",
                "status": "MIGRATIONS_PASS",
                "candidate_defect": "NO",
            }
        )
    except Exception as error:
        evidence["failure_type"] = type(error).__name__
        evidence["failure_message"] = str(error)
        evidence["candidate_defect"] = "YES"
        raise
    finally:
        evidence["completed_at"] = utc_now()
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def record_tests(evidence_path: Path, junit_path: Path) -> None:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    junit = junit_path.read_text(encoding="utf-8")
    match = re.search(r"<testsuite\s+([^>]+)>", junit)
    if match is None:
        raise RuntimeError("JUnit evidence has no test suite")
    attributes = dict(re.findall(r'(tests|failures|errors|skipped)="(\d+)"', match[1]))
    if set(attributes) != {"tests", "failures", "errors", "skipped"}:
        raise RuntimeError("JUnit evidence is missing bounded count attributes")
    tests = int(attributes["tests"])
    failures = int(attributes["failures"])
    errors = int(attributes["errors"])
    skipped = int(attributes["skipped"])
    evidence["targeted_tests"] = {
        "total": tests,
        "passed": tests - failures - errors - skipped,
        "failed": failures + errors,
        "skipped": skipped,
    }
    if failures or errors or skipped:
        evidence["status"] = "FAIL"
        evidence["candidate_defect"] = "YES"
    else:
        evidence["status"] = "PASS"
        evidence["candidate_defect"] = "NO"
    evidence["completed_at"] = utc_now()
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_evidence(evidence_path: Path) -> None:
    raw = evidence_path.read_text(encoding="utf-8")
    prohibited = (
        "postgresql+psycopg://",
        "password",
        "authorization",
        "api_key",
        "token",
    )
    lowered = raw.lower()
    if any(item in lowered for item in prohibited):
        raise RuntimeError("sanitized evidence contains a prohibited field or value")
    evidence = json.loads(raw)
    if evidence.get("candidate_sha") != APPROVED_SHA:
        raise RuntimeError("evidence candidate SHA mismatch")
    print(f"Sanitized certification evidence status: {evidence.get('status')}")


def main() -> None:
    action = sys.argv[1]
    if action == "certify":
        certify(Path(sys.argv[2]))
    elif action == "prepare-predecessor-db":
        prepare_predecessor_database()
    elif action == "record-tests":
        record_tests(Path(sys.argv[2]), Path(sys.argv[3]))
    elif action == "verify-evidence":
        verify_evidence(Path(sys.argv[2]))
    elif action == "cleanup":
        cleanup()
    else:
        raise SystemExit(f"unknown action: {action}")


if __name__ == "__main__":
    main()
