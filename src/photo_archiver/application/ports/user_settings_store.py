"""Port for persisting user preferences independent of system configuration."""

from typing import Protocol

from photo_archiver.application.dtos.settings import UserPreferences


class UserSettingsStore(Protocol):
    """Load and save :class:`UserPreferences` without exposing storage technology."""

    def load(self) -> UserPreferences:
        """Return the persisted user preferences, using defaults for missing keys."""
        ...

    def save(self, preferences: UserPreferences) -> None:
        """Persist the given user preferences."""
        ...
