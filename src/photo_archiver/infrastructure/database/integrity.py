"""Startup database integrity gate (Phase B P0-6, D-B4).

A corrupted database file fails fast with a typed error so the entry layer can
present recovery guidance instead of a raw traceback. The check is strictly
read-only (URI ``mode=ro``): it never mutates the corrupted file, never creates
a missing file, and the database is never rebuilt or silently swapped.
"""

from collections.abc import Sequence
from pathlib import Path
import sqlite3

from loguru import logger

# P0-6（D-B3）：启动备份目录名。integrity 门先落（提交 A），backup.py（提交 B）
# 复用此常量；entry 层用它拼接恢复指引中的备份目录路径。
BACKUP_DIRECTORY_NAME = "backups"
IN_MEMORY_DATABASE = ":memory:"


class CorruptedDatabaseError(RuntimeError):
    """Raised when the startup database fails its integrity verification.

    Attributes:
        database_path: Path of the offending database file.
        issues: Raw quick_check issue lines (or the underlying error text).
    """

    def __init__(self, database_path: Path, issues: Sequence[str]) -> None:
        """Store the offending path and the concrete integrity issues."""
        self.database_path = Path(database_path)
        self.issues = list(issues)
        joined = "；".join(self.issues) if self.issues else "quick_check failed"
        super().__init__(
            f"database integrity check failed for {self.database_path}: {joined}"
        )


def _open_read_only(database_path: Path) -> sqlite3.Connection:
    """Open the database strictly read-only via URI (never creates files)."""
    return sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)


def verify_database_integrity(database_path: Path) -> None:
    """Run ``PRAGMA quick_check`` on an existing file database.

    Missing files and ``:memory:`` databases are skipped: creating a fresh
    database is the normal first-launch flow, not a corruption case.

    Raises:
        CorruptedDatabaseError: quick_check reported issues, or the file is not
            readable as a SQLite database at all (e.g. garbage bytes).
    """
    if str(database_path) == IN_MEMORY_DATABASE or not database_path.exists():
        return
    # P0-8 轮（审查 F-2）：热 -wal 残留（如上次运行崩溃）时，mode=ro 的
    # quick_check 不可靠——可能把"等待恢复"的正常状态误报为损坏。跳过只读
    # 门，交由 bootstrap 紧随其后的读写打开恢复 WAL；真损坏由该路径的
    # sqlite3.DatabaseError 兜底（bootstrap 已归一为 CorruptedDatabaseError），
    # 防御纵深不损失。
    if database_path.with_name(database_path.name + "-wal").exists():
        logger.info(
            "WAL sidecar present for {} — deferring integrity check to the "
            "recovery-capable open",
            database_path,
        )
        return
    try:
        connection = _open_read_only(database_path)
    except sqlite3.DatabaseError as error:
        raise CorruptedDatabaseError(database_path, [str(error)]) from error
    try:
        rows = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.DatabaseError as error:
        raise CorruptedDatabaseError(database_path, [str(error)]) from error
    finally:
        connection.close()
    issues = [str(row[0]) for row in rows if str(row[0]) != "ok"]
    if issues:
        raise CorruptedDatabaseError(database_path, issues)