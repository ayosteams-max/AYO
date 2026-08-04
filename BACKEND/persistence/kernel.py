from sqlalchemy import Engine

from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.kernel_repository import (
    PostgresDomainEventRepository,
    PostgresIdempotencyRepository,
    PostgresTransactionalOutboxRepository,
)
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


class PersistenceUnitOfWork(SqlAlchemyUnitOfWork):
    """Domain-neutral persistence repositories sharing one transaction."""

    def __enter__(self) -> "PersistenceUnitOfWork":
        super().__enter__()
        return self

    @property
    def audit(self) -> PostgresAuditEventRepository:
        return self.repository("audit", PostgresAuditEventRepository)

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        return self.repository("idempotency", PostgresIdempotencyRepository)

    @property
    def events(self) -> PostgresDomainEventRepository:
        return self.repository("events", PostgresDomainEventRepository)

    @property
    def outbox(self) -> PostgresTransactionalOutboxRepository:
        return self.repository("outbox", PostgresTransactionalOutboxRepository)


class PersistenceKernel:
    """Process-scoped factory; every returned repository is transaction-scoped."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "audit": PostgresAuditEventRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
        }

    def unit_of_work(self) -> PersistenceUnitOfWork:
        return PersistenceUnitOfWork(self._engine, self._factories)
