"""SQLite implementation of the UnitOfWork port."""

from contextlib import contextmanager
from collections.abc import Iterator

from photo_archiver.application.ports import UnitOfWork
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider


class SQLiteUnitOfWork(UnitOfWork):
    """Bind a SQLite transaction as the unit of work boundary.

    Delegates to :meth:`SQLiteConnectionProvider.transaction` so that all
    repository calls during the scope share a single connection and commit
    atomically on normal exit or roll back on exception.
    """

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the unit of work with the shared connection provider."""
        self._connection_provider = connection_provider

    def __enter__(self) -> "SQLiteUnitOfWork":
        """Begin the SQLite transaction scope."""
        self._scope = self._connection_provider.transaction()
        self._scope.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit on normal exit or roll back on exception via the scope manager."""
        self._scope.__exit__(exc_type, exc_val, exc_tb)
        self._scope = None
