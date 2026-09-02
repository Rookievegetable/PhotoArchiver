"""P0-5 (Phase B) data-safety pragmas on SQLite connection paths.

Real-link tests against real file databases on ``tmp_path``: WAL journal mode,
per-connection ``busy_timeout``, and a genuine two-connection lock scenario
where a second writer waits out the first writer's open transaction (the G-05
user-visible failure shape: the scan UoW holds the write lock and a concurrent
review write used to die with ``database is locked``).
"""

from pathlib import Path
import threading
import time

from photo_archiver.infrastructure import SQLiteConnectionProvider
from photo_archiver.infrastructure.database.sqlite_connection import BUSY_TIMEOUT_MS

_WAIT_GRACE_SECONDS = 5.0
_LOCK_HOLD_SECONDS = 0.3
_LOCK_ASSERT_FLOOR_SECONDS = _LOCK_HOLD_SECONDS / 2


def _make_provider(tmp_path: Path, name: str = "pragmas.db") -> SQLiteConnectionProvider:
    """Return a connection provider over a real temp file database."""
    return SQLiteConnectionProvider(tmp_path / name)


def test_connect_applies_busy_timeout(tmp_path: Path) -> None:
    """Every per-call connection carries the explicit busy_timeout budget."""
    provider = _make_provider(tmp_path)
    connection = provider.connect()
    try:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
    finally:
        connection.close()


def test_connect_enables_wal_for_file_database(tmp_path: Path) -> None:
    """File databases run in WAL journal mode, persistently and idempotently."""
    provider = _make_provider(tmp_path)
    first = provider.connect()
    try:
        assert first.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        first.close()

    # WAL is persistent on the database file: a second connection on the same
    # path must observe it without any extra setup.
    second = provider.connect()
    try:
        second.execute("CREATE TABLE t (v INTEGER)")
        second.commit()
        assert second.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        second.close()


def test_connect_keeps_foreign_keys_and_row_factory(tmp_path: Path) -> None:
    """Regression guard: the shared configure path preserves existing contract."""
    provider = _make_provider(tmp_path)
    connection = provider.connect()
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        row = connection.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1  # sqlite3.Row factory still installed
    finally:
        connection.close()


def test_in_memory_database_skips_wal() -> None:
    """:memory: databases cannot use WAL and keep their native journal mode."""
    provider = SQLiteConnectionProvider(":memory:")
    connection = provider.connect()
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "memory"
    finally:
        connection.close()


def test_transaction_connection_applies_pragmas(tmp_path: Path) -> None:
    """Transaction-scope connections carry the same data-safety pragmas."""
    provider = SQLiteConnectionProvider(tmp_path / "tx.db")
    provider.initialize_schema()
    with provider.transaction() as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_second_writer_waits_within_busy_timeout(tmp_path: Path) -> None:
    """Real lock scenario: writer B blocks until writer A commits, then succeeds.

    Mirrors the G-05 failure shape — connection A holds an open write
    transaction (as the scan UoW does); connection B's INSERT must wait inside
    the configured busy_timeout instead of raising ``database is locked``.
    Writer B opens its own connection inside its thread (sqlite3 connections
    are pinned to their creating thread by default).
    """
    provider = _make_provider(tmp_path, "lock.db")
    setup = provider.connect()
    try:
        setup.execute("CREATE TABLE t (v INTEGER)")
        setup.commit()
    finally:
        setup.close()

    writer_a = provider.connect()
    lock_held = threading.Event()
    elapsed: dict[str, float] = {}

    def second_writer() -> None:
        assert lock_held.wait(timeout=_WAIT_GRACE_SECONDS)
        writer_b = provider.connect()
        try:
            started = time.perf_counter()
            writer_b.execute("INSERT INTO t VALUES (2)")
            writer_b.commit()
            elapsed["seconds"] = time.perf_counter() - started
        finally:
            writer_b.close()

    thread = threading.Thread(target=second_writer, name="writer-b")
    thread.start()
    try:
        writer_a.execute("BEGIN IMMEDIATE")
        writer_a.execute("INSERT INTO t VALUES (1)")
        lock_held.set()
        time.sleep(_LOCK_HOLD_SECONDS)  # keep A's transaction open past B's start
        writer_a.commit()
    finally:
        thread.join(timeout=BUSY_TIMEOUT_MS / 1000 + _WAIT_GRACE_SECONDS)
        writer_a.close()

    assert not thread.is_alive(), "writer B never acquired the write lock"
    assert "seconds" in elapsed, "writer B failed instead of waiting for the lock"
    assert elapsed["seconds"] >= _LOCK_ASSERT_FLOOR_SECONDS
