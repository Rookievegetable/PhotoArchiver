"""Startup database backup (Phase B P0-6, D-B3).

Snapshot backups via ``VACUUM INTO``: the copy is transactionally consistent
even with WAL sidecar files (plain file copies are not). Backup failure never
blocks startup — it logs a warning — and a partial artifact is cleaned up.
"""

from datetime import datetime
from pathlib import Path
import sqlite3

from loguru import logger

# P0-6（D-B3）：与 integrity 门共享目录名常量，保持恢复指引与实际落盘一致。
from photo_archiver.infrastructure.database.integrity import BACKUP_DIRECTORY_NAME

BACKUP_KEEP_COUNT = 3
BACKUP_FILE_TEMPLATE = "photo_archiver_%Y%m%d_%H%M%S.db"


def backup_database(database_path: Path, keep: int = BACKUP_KEEP_COUNT) -> Path:
    """Create a consistent backup snapshot and prune old backups.

    Args:
        database_path: Path of the database file to back up.
        keep: Rolling window size; older backups beyond this count are deleted.

    Returns:
        Path of the freshly written backup file.

    Raises:
        RuntimeError: The snapshot could not be created (partial artifacts are
            removed first); callers decide whether that is fatal.
        FileNotFoundError: The source database does not exist.
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"database does not exist, nothing to back up: {database_path}")
    backup_directory = database_path.parent / BACKUP_DIRECTORY_NAME
    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(BACKUP_FILE_TEMPLATE)
    base = backup_directory / timestamp
    target = base
    suffix = 0
    # VACUUM INTO refuses to overwrite: multiple backups within the same second
    # (restart loops, tests) collide on the timestamp — disambiguate with _1, _2…
    while target.exists():
        suffix += 1
        target = backup_directory / f"{base.stem}_{suffix}{base.suffix}"
    uri = database_path.resolve().as_uri()
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute("VACUUM INTO ?", (str(target),))
        finally:
            connection.close()
    except Exception as error:
        target.unlink(missing_ok=True)  # never leave a partial snapshot behind
        raise RuntimeError(f"database backup failed for {database_path}: {error}") from error
    _prune_old_backups(backup_directory, keep)
    logger.info("Database backup written: {}", target)
    return target


def copy_database(source: Path, target: Path) -> Path:
    """Copy a database into a consistent snapshot at an exact path (ADR-039).

    Migration primitive for the legacy CWD database: ``VACUUM INTO`` produces
    a transactionally consistent copy even with WAL sidecars. The source is
    opened read-only-ish (a single connection, closed immediately) and is
    never modified — copy, never move (D3). Refuses to overwrite an existing
    target; callers decide how to handle pre-existing files.
    """
    source = Path(source)
    target = Path(target)
    if not source.exists():
        raise FileNotFoundError(f"source database does not exist: {source}")
    if target.exists():
        raise FileExistsError(f"migration target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    uri = source.resolve().as_uri()
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute("VACUUM INTO ?", (str(target),))
        finally:
            connection.close()
    except Exception as error:
        target.unlink(missing_ok=True)  # never leave a partial copy behind
        raise RuntimeError(f"database migration copy failed for {source}: {error}") from error
    logger.info("Database copied: {} -> {}", source, target)
    return target


def _prune_old_backups(backup_directory: Path, keep: int) -> None:
    """Keep only the newest ``keep`` snapshot files in the backup directory."""
    backups = sorted(backup_directory.glob("*.db"))
    for stale in backups[:-keep] if keep > 0 else backups:
        stale.unlink(missing_ok=True)