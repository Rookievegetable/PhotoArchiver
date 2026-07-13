"""SQLite implementation of the UnitOfWork port."""

import threading
from typing import Optional

from photo_archiver.application.ports import UnitOfWork
from photo_archiver.infrastructure.database.sqlite_connection import SQLiteConnectionProvider


class SQLiteUnitOfWork(UnitOfWork):
    """Bind a SQLite transaction as the unit of work boundary.

    Delegates to :meth:`SQLiteConnectionProvider.transaction` so that all
    repository calls during the scope share a single connection and commit
    atomically on normal exit or roll back on exception. The scope handle is
    kept per-thread so concurrent worker tasks each maintain their own unit
    of work against the shared connection provider without cross-thread state.
    """

    def __init__(self, connection_provider: SQLiteConnectionProvider) -> None:
        """Initialize the unit of work with the shared connection provider."""
        self._connection_provider = connection_provider
        self._thread_local = threading.local()

    @property
    def _scope(self):
        """Return the transaction scope handle bound to the current thread."""
        return getattr(self._thread_local, "scope", None)

    @_scope.setter
    def _scope(self, value) -> None:
        """Bind or clear the transaction scope handle for the current thread."""
        if value is None:
            if hasattr(self._thread_local, "scope"):
                del self._thread_local.scope
        else:
            self._thread_local.scope = value

    def __enter__(self) -> "SQLiteUnitOfWork":
        """Begin the SQLite transaction scope on the current thread."""
        scope = self._connection_provider.transaction()
        scope.__enter__()
        self._scope = scope
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit on normal exit or roll back on exception via the scope manager."""
        scope = self._scope
        if scope is None:
            return
        self._scope = None
        scope.__exit__(exc_type, exc_val, exc_tb)
