"""Tests for the startup backup facility (Phase B P0-6, D-B3).

Real-link tests against real SQLite files: snapshot roundtrip, rolling window
pruning, missing-source failure, and partial-artifact cleanup on failure.
"""

from pathlib import Path
import sqlite3

import pytest

import photo_archiver.infrastructure.database.backup as backup_module
from photo_archiver.infrastructure.database.backup import backup_database
from photo_archiver.infrastructure.database.integrity import BACKUP_DIRECTORY_NAME


def _make_database(path: Path) -> None:
    """Create a small real database with known contents."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE demo (v TEXT)")
        connection.execute("INSERT INTO demo VALUES ('a'), ('b'), ('c')")
        connection.commit()
    finally:
        connection.close()


def test_backup_creates_consistent_copy_in_backup_directory(tmp_path: Path) -> None:
    """The snapshot lands in backups/ and round-trips the original contents."""
    source = tmp_path / "photo_archiver.db"
    _make_database(source)

    backup = backup_database(source)

    assert backup.parent == source.parent / BACKUP_DIRECTORY_NAME
    assert backup.name.startswith("photo_archiver_")
    assert backup.name.endswith(".db")
    connection = sqlite3.connect(backup)
    try:
        rows = connection.execute("SELECT v FROM demo").fetchall()
    finally:
        connection.close()
    assert [row[0] for row in rows] == ["a", "b", "c"]


def test_backup_survives_same_second_restarts(tmp_path: Path) -> None:
    """Two snapshots within one second get distinct names (VACUUM INTO no-overwrite)."""
    source = tmp_path / "photo_archiver.db"
    _make_database(source)
    backup_directory = source.parent / BACKUP_DIRECTORY_NAME

    first = backup_database(source)
    second = backup_database(source)

    assert first != second
    assert first.exists() and second.exists()
    assert len(list(backup_directory.glob("*.db"))) == 2


def test_backup_keeps_rolling_window(tmp_path: Path) -> None:
    """Only the newest ``keep`` snapshots survive; the oldest is pruned."""
    source = tmp_path / "photo_archiver.db"
    _make_database(source)
    backup_directory = source.parent / BACKUP_DIRECTORY_NAME

    first = backup_database(source, keep=3)
    second = backup_database(source, keep=3)
    third = backup_database(source, keep=3)
    fourth = backup_database(source, keep=3)

    backups = sorted(backup_directory.glob("*.db"))
    assert len(backups) == 3
    assert first not in backups
    assert {second, third, fourth} == set(backups)


def test_backup_refuses_missing_source(tmp_path: Path) -> None:
    """A missing database never produces an empty snapshot file."""
    with pytest.raises(FileNotFoundError, match="nothing to back up"):
        backup_database(tmp_path / "missing.db")
    assert list((tmp_path / BACKUP_DIRECTORY_NAME).glob("*.db")) == []


def test_backup_failure_cleans_up_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing snapshot removes the partial artifact and raises for the caller."""

    class _StubConnection:
        def execute(self, statement: str) -> None:
            raise sqlite3.DatabaseError("injected backup failure")

        def close(self) -> None:
            return None

    class _StubSqlite3:
        @staticmethod
        def connect(uri: str, uri_flag: bool = False) -> _StubConnection:
            return _StubConnection()

    source = tmp_path / "photo_archiver.db"
    _make_database(source)
    monkeypatch.setattr(backup_module, "sqlite3", _StubSqlite3)

    with pytest.raises(RuntimeError, match="backup failed"):
        backup_database(source)

    assert list((source.parent / BACKUP_DIRECTORY_NAME).glob("*.db")) == []