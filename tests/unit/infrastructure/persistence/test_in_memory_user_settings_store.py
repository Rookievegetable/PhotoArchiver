"""Unit tests for the InMemoryUserSettingsStore persistence adapter."""

from pathlib import Path

from photo_archiver.application.dtos.settings import UserPreferences
from photo_archiver.infrastructure.persistence import InMemoryUserSettingsStore


def test_load_returns_defaults_when_unsaved() -> None:
    """load on a fresh store must return a default UserPreferences."""
    store = InMemoryUserSettingsStore()
    loaded = store.load()
    assert isinstance(loaded, UserPreferences)
    assert loaded == UserPreferences()


def test_load_returns_seeded_snapshot() -> None:
    """load must return the snapshot passed to the constructor."""
    seeded = UserPreferences(theme="dark", language="zh", max_workers=8)
    store = InMemoryUserSettingsStore(seeded)
    assert store.load() == seeded


def test_save_overwrites_snapshot_visible_to_load() -> None:
    """save must replace the in-memory snapshot so the next load sees the new values."""
    store = InMemoryUserSettingsStore()
    new_preferences = UserPreferences(
        theme="light",
        language="en",
        default_import_path=Path("/imports"),
        default_export_path=Path("/exports"),
        match_threshold=0.55,
        max_workers=2,
    )
    store.save(new_preferences)
    assert store.load() == new_preferences


def test_save_then_load_round_trips_path_fields() -> None:
    """Path overrides must survive save -> load without transformation."""
    preferences = UserPreferences(
        default_import_path=Path("/imports/nested"),
        default_export_path=Path("/exports/nested"),
    )
    store = InMemoryUserSettingsStore()
    store.save(preferences)
    loaded = store.load()
    assert loaded.default_import_path == Path("/imports/nested")
    assert loaded.default_export_path == Path("/exports/nested")
