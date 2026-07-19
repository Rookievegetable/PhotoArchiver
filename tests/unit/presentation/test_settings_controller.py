"""Tests for SettingsController — load/save forwarding + error formatting."""

import pytest

pytest.importorskip("PySide6")

from photo_archiver.application.dtos.settings import (
    InvalidPreferencesError,
    UserPreferences,
)
from photo_archiver.presentation.controllers import SettingsController


class _FakeSettingsUseCase:
    """Captures load/save calls and can be programmed to raise on save."""

    def __init__(
        self,
        snapshot: UserPreferences | None = None,
        raise_on_save: bool = False,
    ) -> None:
        self._snapshot = snapshot if snapshot is not None else UserPreferences()
        self.load_calls: int = 0
        self.save_calls: list[UserPreferences] = []
        self._raise_on_save = raise_on_save

    def load(self) -> UserPreferences:
        self.load_calls += 1
        return self._snapshot

    def save(self, preferences: UserPreferences) -> None:
        self.save_calls.append(preferences)
        if self._raise_on_save:
            raise InvalidPreferencesError("theme 'hot-pink' not in ('system', 'light', 'dark')")


def test_load_forwards_to_use_case() -> None:
    """load() must return exactly what the use case returns."""
    seeded = UserPreferences(theme="dark", language="zh")
    use_case = _FakeSettingsUseCase(seeded)
    controller = SettingsController(use_case)  # type: ignore[arg-type]
    assert controller.load() == seeded
    assert use_case.load_calls == 1


def test_save_forwards_candidate_to_use_case() -> None:
    """save() must forward the candidate preferences unchanged."""
    use_case = _FakeSettingsUseCase()
    controller = SettingsController(use_case)  # type: ignore[arg-type]
    candidate = UserPreferences(theme="light", max_workers=2)
    controller.save(candidate)
    assert use_case.save_calls == [candidate]


def test_save_propagates_validation_error() -> None:
    """save must NOT swallow InvalidPreferencesError — the dialog surfaces it."""
    use_case = _FakeSettingsUseCase(raise_on_save=True)
    controller = SettingsController(use_case)  # type: ignore[arg-type]
    with pytest.raises(InvalidPreferencesError):
        controller.save(UserPreferences())


def test_format_validation_error_returns_message_string() -> None:
    """format_validation_error must return the error's string form verbatim."""
    error = InvalidPreferencesError("theme invalid; max_workers invalid")
    formatted = SettingsController.format_validation_error(error)
    assert formatted == "theme invalid; max_workers invalid"
