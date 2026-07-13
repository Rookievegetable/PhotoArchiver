"""SQLite connection and schema management for repository implementations."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
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
    reuses the single active connection so that repository operations participate
    in the same transaction boundary and commit atomically on success.
    """

    def __init__(self, database_path: Path | str) -> None:
        """Store the SQLite database path."""
        self.database_path = Path(database_path) if database_path != ":memory:" else Path(":memory:")
        self._active_connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection | _SharedConnection:
        """Return a SQLite connection configured for repository use.

        If a transaction is active, returns a wrapper bound to the shared connection
        so callers can use ``with`` without closing the transaction-owned connection.
        """
        if self._active_connection is not None:
            return _SharedConnection(self._active_connection)
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Bind a single connection as the transaction scope for nested repository calls.

        On normal exit the connection is committed; on exception it is rolled back.
        The connection is closed in either case and the provider is restored to
        per-call connection mode.
        """
        if self._active_connection is not None:
            raise RuntimeError("Nested SQLite transactions are not supported")

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
