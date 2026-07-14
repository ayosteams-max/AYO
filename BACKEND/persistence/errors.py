class PersistenceError(RuntimeError):
    """Base error for safe persistence failure classification."""


class OptimisticConcurrencyError(PersistenceError):
    """The stored aggregate changed after it was read."""


class RepositoryConfigurationError(PersistenceError):
    """Repository composition is missing or invalid."""
