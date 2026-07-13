"""SQLite connection and schema management for repository implementations."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from typing import Optional


class _SharedConnection:
    """Wrap the active transaction connection so repository ``with`` blocks do not close it.

    The real close happens once in :meth:`SQLiteConnectionProvider.transaction`
    when the unit of work scope exits.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Store the shared connection."""
        self._connection = connection

    def __enter__(self) -> "sqlite3.Connection":
        """Return the underlying connection."""
        return self._connection

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Suppress close so the transaction owner retains the connection."""


class SQLiteConnectionProvider:
    """Create SQLite connections and initialize the repository schema.

    When a transaction is active (entered via :meth:`transaction`), :meth:`connect`
    reuses the single active connection bound to the **current thread** so that
    repository operations participate in the same transaction boundary and commit
    atomically on success. Per-thread binding keeps ``sqlite3.Connection`` usage
    single-threaded (sqlite3.Connection is not thread-safe across threads) while
    still allowing concurrent worker tasks to each open their own transaction.
    """

    def __init__(self, database_path: Path | str) -> None:
        """Store the SQLite database path and per-thread transaction state."""
        self.database_path = Path(database_path) if database_path != ":memory:" else Path(":memory:")
        self._thread_local = threading.local()

    @property
    def _active_connection(self) -> Optional[sqlite3.Connection]:
        """Return the transaction connection bound to the current thread, if any."""
        return getattr(self._thread_local, "connection", None)

    @_active_connection.setter
    def _active_connection(self, value: Optional[sqlite3.Connection]) -> None:
        """Bind or clear the transaction connection for the current thread."""
        if value is None:
            if hasattr(self._thread_local, "connection"):
                del self._thread_local.connection
        else:
            self._thread_local.connection = value

    def connect(self) -> sqlite3.Connection | _SharedConnection:
        """Return a SQLite connection configured for repository use.

        If a transaction is active on the current thread, returns a wrapper bound
        to the shared connection so callers can use ``with`` without closing the
        transaction-owned connection.
        """
        active = self._active_connection
        if active is not None:
            return _SharedConnection(active)
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Bind a single connection as the transaction scope for nested repository calls.

        The connection is bound to the current thread; concurrent threads may open
        their own transactions independently. On normal exit the connection is
        committed; on exception it is rolled back. The connection is closed in
        either case and the provider is restored to per-call connection mode.
        """
        if self._active_connection is not None:
            raise RuntimeError("Nested SQLite transactions are not supported on a single thread")

        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN")
        self._active_connection = connection
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            self._active_connection = None
            connection.close()

    def initialize_schema(self) -> None:
        """Create repository tables and indexes when they do not exist."""
        if str(self.database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS people (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    identity TEXT UNIQUE,
                    department TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    raw_path TEXT NOT NULL,
                    path_base TEXT NOT NULL,
                    display_name TEXT,
                    total_photos INTEGER NOT NULL,
                    scanned_photos INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(raw_path, path_base)
                );

                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY,
                    raw_path TEXT NOT NULL,
                    path_base TEXT NOT NULL,
                    folder_id TEXT,
                    original_name TEXT,
                    created_at TEXT NOT NULL,
                    metadata_width INTEGER,
                    metadata_height INTEGER,
                    metadata_file_size_bytes INTEGER,
                    metadata_modified_at TEXT,
                    metadata_content_hash TEXT,
                    UNIQUE(raw_path, path_base),
                    FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_photos_folder_id ON photos(folder_id);
                """
            )
            connection.execute("PRAGMA user_version = 1")
