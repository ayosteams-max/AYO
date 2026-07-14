from sqlalchemy import Engine, create_engine

from BACKEND.persistence.config import DatabaseSettings


def create_postgres_engine(settings: DatabaseSettings) -> Engine:
    """Create one process-scoped PostgreSQL engine and bounded connection pool."""

    options = (
        "-c timezone=UTC "
        f"-c statement_timeout={settings.statement_timeout_ms} "
        "-c idle_in_transaction_session_timeout="
        f"{settings.idle_transaction_timeout_ms}"
    )
    return create_engine(
        settings.require_url(),
        connect_args={
            "application_name": settings.application_name,
            "connect_timeout": settings.connect_timeout_seconds,
            "options": options,
            "sslmode": settings.ssl_mode,
        },
        hide_parameters=True,
        max_overflow=settings.max_overflow,
        pool_pre_ping=True,
        pool_recycle=settings.pool_recycle_seconds,
        pool_size=settings.pool_size,
        pool_timeout=settings.pool_timeout_seconds,
    )
