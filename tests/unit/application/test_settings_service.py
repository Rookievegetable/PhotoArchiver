"""Unit tests for the SettingsService Application-layer orchestration."""

from pathlib import Path

import pytest

from photo_archiver.application.dtos.settings import (
    DEFAULT_LANGUAGE,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    DEFAULT_THEME,
    InvalidPreferencesError,
    UserPreferences,
)
from photo_archiver.application.ports.system_settings import SystemSettings
from photo_archiver.application.ports.user_settings_store import UserSettingsStore
from photo_archiver.application.services import SettingsService


class _RecordingStore(UserSettingsStore):
    """In-memory UserSettingsStore capturing save() calls for assertion."""

    def __init__(self, snapshot: UserPreferences | None = None) -> None:
        self._snapshot = snapshot if snapshot is not None else UserPreferences()
        self.saved: list[UserPreferences] = []

    def load(self) -> UserPreferences:
        return self._snapshot

    def save(self, preferences: UserPreferences) -> None:
        self.saved.append(preferences)
        self._snapshot = preferences


class _StubSystemSettings(SystemSettings):
    """Stub SystemSettings returning fixed threshold / workers fallbacks."""

    def __init__(self, threshold: float, workers: int) -> None:
        self._threshold = threshold
        self._workers = workers

    @property
    def match_threshold(self) -> float:
        return self._threshold

    @property
    def max_workers(self) -> int:
        return self._workers


def test_load_returns_persisted_values_when_store_has_overrides() -> None:
    """load must return the persisted snapshot unchanged when every field is set."""
    persisted = UserPreferences(
        theme="dark",
        language="zh",
        default_import_path=Path("/imports"),
        default_export_path=Path("/exports"),
        match_threshold=0.55,
        max_workers=8,
    )
    service = SettingsService(_RecordingStore(persisted), _StubSystemSettings(0.42, 16))
    loaded = service.load()
    assert loaded == persisted


def test_load_falls_back_to_system_threshold_when_user_never_set() -> None:
    """load must override the default threshold with the system value when the user never set it.

    The store contract requires missing keys to come back as the dataclass default;
    ``SettingsService.load`` then re-applies the system-level fallback so a
    configured system bound is honored even when the user has never opened the
    settings dialog.
    """
    persisted = UserPreferences(match_threshold=DEFAULT_MATCH_THRESHOLD, max_workers=8)
    service = SettingsService(_RecordingStore(persisted), _StubSystemSettings(0.42, 16))
    loaded = service.load()
    assert loaded.match_threshold == 0.42
    assert loaded.max_workers == 8  # user-overridden, not system-default


def test_load_falls_back_to_system_workers_when_user_never_set() -> None:
    """load must override the default workers count with the system value when unset."""
    persisted = UserPreferences(match_threshold=0.6, max_workers=DEFAULT_MAX_WORKERS)
    service = SettingsService(_RecordingStore(persisted), _StubSystemSettings(0.42, 16))
    loaded = service.load()
    assert loaded.match_threshold == 0.6
    assert loaded.max_workers == 16


def test_load_returns_persisted_when_no_system_settings() -> None:
    """load without system_settings must return the store snapshot verbatim."""
    persisted = UserPreferences(theme="light", max_workers=2)
    service = SettingsService(_RecordingStore(persisted), None)
    assert service.load() == persisted


def test_save_persists_valid_preferences() -> None:
    """save must forward valid preferences to the store."""
    store = _RecordingStore()
    service = SettingsService(store, None)
    candidate = UserPreferences(theme="dark", language="en", max_workers=4)
    service.save(candidate)
    assert store.saved == [candidate]
    assert store.load() == candidate


def test_save_rejects_invalid_theme_and_does_not_touch_store() -> None:
    """save must validate before persisting so invalid input never lands on disk."""
    store = _RecordingStore()
    service = SettingsService(store, None)
    invalid = UserPreferences(theme="hot-pink", language="system")
    with pytest.raises(InvalidPreferencesError):
        service.save(invalid)
    assert store.saved == []


def test_save_rejects_out_of_range_threshold() -> None:
    """save must raise when match_threshold falls outside [0.0, 1.0]."""
    service = SettingsService(_RecordingStore(), None)
    invalid = UserPreferences(match_threshold=1.5)
    with pytest.raises(InvalidPreferencesError):
        service.save(invalid)


def test_save_rejects_out_of_range_workers() -> None:
    """save must raise when max_workers falls outside [1, 32]."""
    service = SettingsService(_RecordingStore(), None)
    invalid = UserPreferences(max_workers=64)
    with pytest.raises(InvalidPreferencesError):
        service.save(invalid)


def test_validate_preferences_lists_every_violation() -> None:
    """validate_preferences must combine all field violations into one message."""
    invalid = UserPreferences(theme="hot-pink", language="klingon", match_threshold=-0.1, max_workers=0)
    from photo_archiver.application.dtos.settings import validate_preferences

    with pytest.raises(InvalidPreferencesError) as exc_info:
        validate_preferences(invalid)
    message = str(exc_info.value)
    assert "theme" in message
    assert "language" in message
    assert "match_threshold" in message
    assert "max_workers" in message


def test_validate_preferences_accepts_defaults() -> None:
    """validate_preferences must accept a fresh UserPreferences with all defaults."""
    from photo_archiver.application.dtos.settings import validate_preferences

    validate_preferences(UserPreferences())  # must NOT raise


def test_validate_preferences_rejects_parent_traversal_in_paths() -> None:
    """validate_preferences must reject ``..`` segments in path fields (review m-2)."""
    from pathlib import Path

    from photo_archiver.application.dtos.settings import (
        InvalidPreferencesError,
        validate_preferences,
    )

    with pytest.raises(InvalidPreferencesError) as exc_info:
        validate_preferences(
            UserPreferences(default_import_path=Path("../../etc")),
        )
    assert "default_import_path" in str(exc_info.value)
    assert ".." in str(exc_info.value)


def test_validate_preferences_accepts_absolute_paths() -> None:
    """validate_preferences must accept absolute paths without ``..`` (review m-2)."""
    from pathlib import Path

    from photo_archiver.application.dtos.settings import validate_preferences

    validate_preferences(
        UserPreferences(
            default_import_path=Path("/imports"),
            default_export_path=Path("/exports"),
        ),
    )  # must NOT raise


def test_default_preferences_constants_are_consistent() -> None:
    """UserPreferences defaults must equal the module-level DEFAULT_* constants."""
    preferences = UserPreferences()
    assert preferences.theme == DEFAULT_THEME
    assert preferences.language == DEFAULT_LANGUAGE
    assert preferences.match_threshold == DEFAULT_MATCH_THRESHOLD
    assert preferences.max_workers == DEFAULT_MAX_WORKERS
    assert preferences.default_import_path is None
    assert preferences.default_export_path is None
