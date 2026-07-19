"""Use case boundary for loading and saving user preferences."""

from typing import Protocol

from photo_archiver.application.dtos.settings import UserPreferences


class SettingsUseCase(Protocol):
    """Coordinate reading and persisting user preferences.

    The use case bridges the UI (``SettingsController``) and the persistence
    port (``UserSettingsStore``), falling back to system-level defaults
    (``SystemSettings``) when a user preference has never been set. It also
    validates candidate values before they reach the store so invalid input
    can never be persisted.
    """

    def load(self) -> UserPreferences:
        """Return the persisted user preferences, falling back to system defaults."""
        ...

    def save(self, preferences: UserPreferences) -> None:
        """Validate and persist the given user preferences.

        Args:
            preferences: Candidate preferences value object.

        Raises:
            InvalidPreferencesError: When any field violates its bound.
        """
        ...
