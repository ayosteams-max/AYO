import logging
import time
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from BACKEND.persistence.errors import PersistenceError
from BACKEND.persistence.tables import VERSION_TABLE

MIGRATION_LOCK_ID = 18_412_138_359_126_354
logger = logging.getLogger(__name__)


class MigrationLockTimeout(PersistenceError):
    """Another deployment retained the migration lock past the safe deadline."""


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "database" / "migrations"))
    return config


def expected_schema_revision() -> str:
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    if len(heads) != 1:
        raise PersistenceError("AYO migrations must have exactly one reviewed head")
    return heads[0]


class MigrationRunner:
    """Run reviewed migrations under a PostgreSQL session advisory lock."""

    def __init__(self, engine: Engine, lock_timeout_seconds: float = 30.0) -> None:
        self._engine = engine
        self._lock_timeout_seconds = lock_timeout_seconds

    def upgrade(self, revision: str = "head") -> None:
        with self._engine.connect() as connection:
            deadline = time.monotonic() + self._lock_timeout_seconds
            locked = False
            try:
                while time.monotonic() < deadline:
                    locked = bool(
                        connection.execute(
                            text("SELECT pg_try_advisory_lock(:lock_id)"),
                            {"lock_id": MIGRATION_LOCK_ID},
                        ).scalar_one()
                    )
                    connection.commit()
                    if locked:
                        break
                    time.sleep(0.1)
                if not locked:
                    raise MigrationLockTimeout(
                        "Timed out waiting for the database migration lock"
                    )

                config = alembic_config()
                config.attributes["connection"] = connection
                logger.info("database_migration_started", extra={"revision": revision})
                command.upgrade(config, revision)
                logger.info(
                    "database_migration_completed", extra={"revision": revision}
                )
            except Exception:
                connection.rollback()
                logger.exception(
                    "database_migration_failed", extra={"revision": revision}
                )
                raise
            finally:
                if locked:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": MIGRATION_LOCK_ID},
                    )
                    connection.commit()


@dataclass(frozen=True)
class SchemaReadiness:
    ready: bool
    current_revision: str | None
    expected_revision: str
    reason: str | None = None


class SchemaVersionReadinessChecker:
    """Internal, read-only schema readiness check; it is not an API endpoint."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> SchemaReadiness:
        expected = expected_schema_revision()
        try:
            with self._engine.connect() as connection:
                current = MigrationContext.configure(
                    connection, opts={"version_table": VERSION_TABLE}
                ).get_current_revision()
                required_tables = connection.execute(
                    text(
                        "SELECT to_regclass('ayo.rides') IS NOT NULL "
                        "AND to_regclass('ayo.legacy_wallets') IS NOT NULL "
                        "AND to_regclass('ayo.audit_events') IS NOT NULL"
                        " AND to_regclass('ayo.persistence_idempotency_records') IS NOT NULL"
                        " AND to_regclass('ayo.persistence_domain_events') IS NOT NULL"
                        " AND to_regclass('ayo.persistence_outbox') IS NOT NULL"
                        " AND to_regclass('ayo.canonical_subjects') IS NOT NULL"
                        " AND to_regclass('ayo.identity_accounts') IS NOT NULL"
                        " AND to_regclass('ayo.legacy_identity_mappings') IS NOT NULL"
                        " AND to_regclass('ayo.sessions') IS NOT NULL"
                        " AND to_regclass('ayo.rate_limit_buckets') IS NOT NULL"
                        " AND to_regclass('ayo.identities') IS NOT NULL"
                        " AND to_regclass('ayo.identity_authentication_methods') IS NOT NULL"
                        " AND to_regclass('ayo.authentication_challenges') IS NOT NULL"
                        " AND to_regclass('ayo.token_families') IS NOT NULL"
                        " AND to_regclass('ayo.permissions') IS NOT NULL"
                        " AND to_regclass('ayo.roles') IS NOT NULL"
                        " AND to_regclass('ayo.role_permissions') IS NOT NULL"
                        " AND to_regclass('ayo.identity_role_assignments') IS NOT NULL"
                        " AND to_regclass('ayo.support_cases') IS NOT NULL"
                        " AND to_regclass('ayo.support_case_events') IS NOT NULL"
                        " AND to_regclass('ayo.support_case_messages') IS NOT NULL"
                        " AND to_regclass('ayo.support_ai_interactions') IS NOT NULL"
                        " AND to_regclass('ayo.dispatch_ride_requests') IS NOT NULL"
                        " AND to_regclass('ayo.dispatch_attempts') IS NOT NULL"
                        " AND to_regclass('ayo.dispatch_driver_offers') IS NOT NULL"
                        " AND to_regclass('ayo.dispatch_assignments') IS NOT NULL"
                        " AND to_regclass('ayo.dispatch_idempotency_records') IS NOT NULL"
                        " AND to_regclass('ayo.dispatch_outbox') IS NOT NULL"
                        " AND to_regclass('ayo.arrival_evaluations') IS NOT NULL"
                        " AND to_regclass('ayo.waiting_sessions') IS NOT NULL"
                        " AND to_regclass('ayo.consequence_suppression_decisions') IS NOT NULL"
                    )
                ).scalar_one()
            ready = current == expected and bool(required_tables)
            return SchemaReadiness(
                ready=ready,
                current_revision=current,
                expected_revision=expected,
                reason=None if ready else "schema_revision_or_objects_not_ready",
            )
        except Exception:
            logger.exception("database_schema_readiness_failed")
            return SchemaReadiness(
                ready=False,
                current_revision=None,
                expected_revision=expected,
                reason="schema_check_unavailable",
            )
