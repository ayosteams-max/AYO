from collections.abc import Callable, Mapping
from types import TracebackType
from typing import TypeVar, cast

from sqlalchemy import Connection, Engine
from sqlalchemy.engine import Transaction

from BACKEND.persistence.errors import RepositoryConfigurationError

RepositoryFactory = Callable[[Connection], object]
RepositoryType = TypeVar("RepositoryType")


class SqlAlchemyUnitOfWork:
    """Reusable transaction and repository-composition boundary.

    Product modules contribute typed repository factories. The kernel owns only
    connection and transaction lifecycle, avoiding a generic CRUD abstraction.
    """

    def __init__(
        self,
        engine: Engine,
        repository_factories: Mapping[str, RepositoryFactory],
    ) -> None:
        self._engine = engine
        self._repository_factories = dict(repository_factories)
        self._connection: Connection | None = None
        self._transaction: Transaction | None = None
        self._repositories: dict[str, object] = {}
        self._finished = False

    @property
    def connection(self) -> Connection:
        if self._connection is None:
            raise RuntimeError("Unit of Work has not been entered.")
        return self._connection

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        if self._connection is not None:
            raise RuntimeError("Unit of Work cannot be entered more than once.")
        self._connection = self._engine.connect()
        self._transaction = self._connection.begin()
        self._repositories = {
            name: factory(self._connection)
            for name, factory in self._repository_factories.items()
        }
        return self

    def repository(
        self, name: str, repository_type: type[RepositoryType]
    ) -> RepositoryType:
        try:
            repository = self._repositories[name]
        except KeyError as error:
            raise RepositoryConfigurationError(
                f"Repository is not registered: {name}"
            ) from error
        if not isinstance(repository, repository_type):
            raise RepositoryConfigurationError(
                f"Repository has unexpected implementation: {name}"
            )
        return cast(RepositoryType, repository)

    def commit(self) -> None:
        if self._transaction is None or self._finished:
            raise RuntimeError("Unit of Work has no active transaction.")
        self._transaction.commit()
        self._finished = True

    def rollback(self) -> None:
        if self._transaction is None or self._finished:
            return
        self._transaction.rollback()
        self._finished = True

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception, traceback
        try:
            if exception_type is None:
                if not self._finished:
                    self.commit()
            else:
                self.rollback()
        finally:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._transaction = None
            self._repositories = {}
