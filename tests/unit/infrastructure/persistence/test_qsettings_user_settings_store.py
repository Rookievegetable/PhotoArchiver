"""QSettingsUserSettingsStore round-trip (G-2 archive_root included)."""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtCore import QSettings

from photo_archiver.application.dtos.settings import UserPreferences
from photo_archiver.infrastructure.persistence.qsettings_user_settings_store import (
    QSettingsUserSettingsStore,
)


def _make_store(tmp_path: Path) -> tuple[QSettingsUserSettingsStore, Path]:
    ini_path = tmp_path / "prefs.ini"
    qsettings = QSettings(str(ini_path), QSettings.Format.IniFormat)
    return QSettingsUserSettingsStore(qsettings), ini_path


def test_archive_root_round_trips(tmp_path: Path) -> None:
    store, _ = _make_store(tmp_path)
    original = UserPreferences(archive_root=Path("D:/archive"))
    store.save(original)

    loaded = store.load()
    assert loaded.archive_root == Path("D:/archive")


def test_archive_root_unset_by_default(tmp_path: Path) -> None:
    store, _ = _make_store(tmp_path)
    assert store.load().archive_root is None


def test_archive_root_blank_value_reads_as_none(tmp_path: Path) -> None:
    store, _ = _make_store(tmp_path)
    store.save(UserPreferences(archive_root=Path("X:/goes")))
    # Simulate a user clearing the field: empty string persisted.
    store._settings.setValue("user_preferences/pref_archive_root", "")
    assert store.load().archive_root is None
