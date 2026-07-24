class PersistenceError(RuntimeError):
    """Base error for safe persistence failure classification."""


class OptimisticConcurrencyError(PersistenceError):
    """The stored aggregate changed after it was read."""


class RepositoryConfigurationError(PersistenceError):
    """Repository composition is missing or invalid."""


class AuditIdempotencyConflict(PersistenceError):
    """An audit idempotency key was reused for different event content."""


class IdempotencyConflictError(PersistenceError):
    """A command key was reused for a different request or result."""


class DuplicateEventError(PersistenceError):
    """An immutable domain event identity was already persisted."""


class SessionPersistenceConflict(PersistenceError):
    """Session state conflicted with an existing durable record."""
