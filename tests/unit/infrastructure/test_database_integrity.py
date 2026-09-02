"""Tests for the startup database integrity gate (Phase B P0-6).

Real-link tests: real file databases on ``tmp_path`` — including genuinely
damaged files — never mocked, per the project's five-layer completion rule.
"""

from pathlib import Path
import sqlite3

import pytest

from photo_archiver.infrastructure.database.integrity import (
    CorruptedDatabaseError,
    verify_database_integrity,
)


def test_missing_database_file_is_skipped(tmp_path: Path) -> None:
    """A not-yet-created database is the normal first-launch flow, not corruption."""
    missing = tmp_path / "absent.db"
    verify_database_integrity(missing)
    assert not missing.exists()  # read-only gate must never create the file


def test_in_memory_database_is_skipped() -> None:
    """:memory: databases have no file to verify."""
    verify_database_integrity(":memory:")


def test_healthy_database_passes_quick_check(tmp_path: Path) -> None:
    """A healthy database passes the gate without errors."""
    path = tmp_path / "healthy.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE t (v INTEGER)")
        connection.commit()
    finally:
        connection.close()
    verify_database_integrity(path)


def test_garbage_bytes_fail_with_typed_error(tmp_path: Path) -> None:
    """A non-SQLite file raises the typed error carrying the underlying message."""
    path = tmp_path / "garbage.db"
    path.write_bytes(b"definitely not a sqlite database" * 8)
    with pytest.raises(CorruptedDatabaseError) as exc_info:
        verify_database_integrity(path)
    assert exc_info.value.database_path == path
    assert exc_info.value.issues


def test_corrupted_database_fails_quick_check(tmp_path: Path) -> None:
    """Real quick_check corruption (header damage on page 2) is reported."""
    path = tmp_path / "corrupted.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA page_size = 512")
        connection.execute(
            "CREATE TABLE t AS WITH RECURSIVE cnt(x) AS "
            "(SELECT 1 UNION ALL SELECT x + 1 FROM cnt LIMIT 200) "
            "SELECT x AS value FROM cnt"
        )
        connection.commit()
    finally:
        connection.close()

    raw = path.read_bytes()
    offset = 512  # second page, safely past the SQLite file header on page 1
    assert len(raw) > offset + 8
    path.write_bytes(raw[:offset] + b"CORRUPT!" + raw[offset + 8 :])

    with pytest.raises(CorruptedDatabaseError) as exc_info:
        verify_database_integrity(path)
    assert exc_info.value.database_path == path
    assert exc_info.value.issues