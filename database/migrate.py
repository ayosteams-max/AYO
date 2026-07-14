"""Explicit migration entry point for controlled deployment jobs only."""

from BACKEND.persistence.config import DatabaseSettings
from BACKEND.persistence.engine import create_postgres_engine
from BACKEND.persistence.migrations import MigrationRunner


def main() -> None:
    settings = DatabaseSettings(application_name="ayo-migration")
    engine = create_postgres_engine(settings)
    try:
        MigrationRunner(
            engine,
            lock_timeout_seconds=settings.migration_lock_timeout_seconds,
        ).upgrade()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
