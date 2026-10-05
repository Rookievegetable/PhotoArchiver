"""SQLite connection and schema management for repository implementations."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
import time
from typing import Optional, TypeVar

from photo_archiver.domain.exceptions import ConcurrentDecisionConflictError

T = TypeVar("T")

# P0-5 (Phase B, data-safety floor): WAL decouples readers from the writer so a
# long scan transaction no longer makes concurrent review/import writes fail
# with "database is locked" (gap G-05). WAL is a persistent property of the
# database file — re-issuing the pragma on every connection is idempotent and
# also upgrades databases created before this change. busy_timeout is
# per-connection state and must therefore be set on every new connection; it is
# deliberately installed *before* the journal-mode pragma so a concurrent
# journal conversion waits on the lock instead of erroring out.
BUSY_TIMEOUT_MS = 5000
WAL_JOURNAL_MODE = "WAL"
IN_MEMORY_DATABASE = ":memory:"


def _configure_connection(connection: sqlite3.Connection, database_path: Path | str) -> None:
    """Apply the shared per-connection pragmas used by every connection path."""
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    if str(database_path) != IN_MEMORY_DATABASE:
        connection.execute(f"PRAGMA journal_mode = {WAL_JOURNAL_MODE}")


def _is_busy_error(exc: sqlite3.OperationalError) -> bool:
    """Return True when ``exc`` is a lock/timeout conflict worth retrying."""
    message = str(exc).lower()
    return "locked" in message or "busy" in message


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
        _configure_connection(connection, self.database_path)
        return connection

    @contextmanager
    def transaction(self, begin_mode: str = "DEFERRED") -> Iterator[sqlite3.Connection]:
        """Bind a single connection as the transaction scope for nested repository calls.

        The connection is bound to the current thread; concurrent threads may open
        their own transactions independently. On normal exit the connection is
        committed; on exception it is rolled back. The connection is closed in
        either case and the provider is restored to per-call connection mode.

        ``begin_mode``（S1-F）：``"DEFERRED"``（缺省，历史行为）或 ``"IMMEDIATE"``
        ——后者在 BEGIN 时立即获取写锁，串行化并发读-改-写（S1 §3：deferred 在
        WAL 下升级写锁会立即失败且 busy_timeout 不重试快照冲突）。

        Nested transactions on the same thread are NOT supported — SQLite
        SAVEPOINTs are deliberately avoided to keep the boundary simple and
        single-threaded. Callers MUST NOT enter a second ``transaction()`` scope
        inside an active one; a RuntimeError is raised to make the violation
        explicit. Code that needs retry-within-transaction should open a fresh
        provider rather than nesting.
        """
        if self._active_connection is not None:
            raise RuntimeError("Nested SQLite transactions are not supported on a single thread")

        connection = sqlite3.connect(str(self.database_path))
        _configure_connection(connection, self.database_path)
        connection.execute(f"BEGIN {begin_mode}")
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

    def run_immediate(
        self,
        operation: Callable[[sqlite3.Connection], T],
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 0.15,
    ) -> T:
        """Execute ``operation`` inside one IMMEDIATE transaction, retrying as a whole.

        S1-F9 契约：读 → 校验 → Assignment 变更 → reconcile → COMMIT 的**完整
        attempt** 是重试单位——busy 冲突时 ROLLBACK（由 :meth:`transaction` 完成）、
        退避、然后从 BEGIN 重新开始并**重新读取最新状态**。禁止只重试某一条 SQL。

        ``operation`` receives the live transaction connection and must reach the
        database through repositories bound to this provider (they join the
        thread-local transaction automatically via :meth:`connect`).

        Raises:
            ConcurrentDecisionConflictError: when every attempt hits a lock
                conflict; no partial write ever survives.
        """
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                with self.transaction(begin_mode="IMMEDIATE") as connection:
                    return operation(connection)
            except sqlite3.OperationalError as exc:
                if not _is_busy_error(exc):
                    raise
                last_error = exc
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
        raise ConcurrentDecisionConflictError(
            f"concurrent decision conflict after {max_attempts} attempts"
        ) from last_error

    def initialize_schema(self) -> None:
        """Initialize the database schema via Alembic migrations (ADR-027).

        阶段 2 加固（ADR-027，前置门拍板 2026-08-12，定稿草案
        ``docs/development/phase2-adr-draft.md``）：

        - 裁决点 1=A：移除 raw SQL ``CREATE TABLE IF NOT EXISTS`` 重复路径——
          6 表 + 6 索引 DDL 全迁入 Alembic migration ``002_split_create_ddl``，
          本方法不再持 DDL，仅留 mkdir + PRAGMA 仅新库 stamp + 调 Alembic 触发迁移。
        - 裁决点 3=C：保留仅新库（``current_version == 0``）``PRAGMA user_version = 4``
          兼容旧库迁移探测（ADR-024 已述兼容旧代码）。Alembic 的 ``alembic_version``
          表独立管 migration 版本，``PRAGMA user_version`` 仅作旧库（v1-v3）迁移兼容。

        Args:
            无参——用 ``self.database_path``。

        Raises:
            Alembic 迁移失败时异常上抛（``alembic_runner.run_alembic_migrations`` 内已 log）。
        """
        if str(self.database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # 仅新库 stamp PRAGMA user_version=4 兼容旧库迁移探测（ADR-024 兼容路径）。
        # review Major fix（ADR-024 遗嘱）：只在 current_version == 0 时 stamp，
        # 避免无条件 ``PRAGMA user_version = 4`` 标 pre-existing v1/v2/v3 库为 v4
        # 而隐藏 schema drift。
        with self.connect() as connection:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version == 0:
                connection.execute("PRAGMA user_version = 4")

        # ADR-027：DDL 全由 Alembic migration 002_split_create_ddl 接管——本方法
        # 不再持 CREATE TABLE 重复路径，调 run_alembic_migrations 触发迁移。
        # :memory: 库由 bootstrap 在 initialize_schema 后单独调 alembic（env.py
        # 已持 sqlite:///:memory: 处置），此处跳过 :memory: 避免路径错。
        if str(self.database_path) != ":memory:":
            from photo_archiver.infrastructure.database.alembic_runner import run_alembic_migrations

            run_alembic_migrations(self.database_path)
