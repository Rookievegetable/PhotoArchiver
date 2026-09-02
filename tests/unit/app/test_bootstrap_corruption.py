"""Bootstrap corruption-gate tests (Phase B P0-6).

Complements ``test_bootstrap.py``: a corrupted database file must fail fast
with the typed error *before* any schema/migration write, and SQLite-layer
failures that slip past the read-only gate must still normalize to the same
typed error (defense in depth, D-B4).
"""

from pathlib import Path
import sqlite3

import pytest

import photo_archiver.app.bootstrap as bootstrap_module
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.infrastructure.database.integrity import CorruptedDatabaseError


def build_settings(tmp_path: Path) -> AppSettings:
    """Build isolated settings for corruption tests."""
    return AppSettings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'data' / 'corrupt.db'}",
        log_directory=tmp_path / "logs",
        model_path=tmp_path / "models",
    )


def test_bootstrap_fails_typed_before_any_write_on_corrupted_database(
    tmp_path: Path,
) -> None:
    """Garbage database file: typed error, no schema or migration side effects."""
    db_path = tmp_path / "data" / "corrupt.db"
    db_path.parent.mkdir()
    db_path.write_bytes(b"junk" * 64)
    settings = build_settings(tmp_path)

    with pytest.raises(CorruptedDatabaseError) as exc_info:
        bootstrap_module.bootstrap_application(settings)

    assert exc_info.value.database_path == db_path


def test_bootstrap_normalizes_sqlite_layer_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DatabaseError past the gate (e.g. during repos/migrations) is re-typed."""
    settings = build_settings(tmp_path)

    def fail_build_sqlite_repositories(database_path: Path) -> object:
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(
        bootstrap_module,
        "build_sqlite_repositories",
        fail_build_sqlite_repositories,
    )

    with pytest.raises(CorruptedDatabaseError):
        bootstrap_module.bootstrap_application(settings)