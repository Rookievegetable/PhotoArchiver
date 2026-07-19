"""In-memory ``UserSettingsStore`` adapter for tests, CLI, and CI contexts.

Holds a single ``UserPreferences`` value in process memory. ``save`` overwrites
the snapshot and ``load`` returns it (or the defaults when nothing has been
saved yet). This adapter is the default used by ``bootstrap_application`` so
CLI and CI runs do not require a Qt runtime or a writable platform settings
location; the desktop UI swaps it for ``QSettingsUserSettingsStore`` in
``app/ui_assembly.py``.
"""

from photo_archiver.application.dtos.settings import UserPreferences
from photo_archiver.application.ports.user_settings_store import UserSettingsStore


class InMemoryUserSettingsStore(UserSettingsStore):
    """Process-memory implementation of the user preferences persistence port."""

    def __init__(self, preferences: UserPreferences | None = None) -> None:
        """Initialize the store with optional pre-seeded preferences.

        Args:
            preferences: Snapshot to return from ``load``; defaults to a fresh
                ``UserPreferences`` when None so callers always receive a
                fully populated value object.
        """
        self._preferences = preferences if preferences is not None else UserPreferences()

    def load(self) -> UserPreferences:
        """Return the in-memory preferences snapshot."""
        return self._preferences

    def save(self, preferences: UserPreferences) -> None:
        """Overwrite the in-memory snapshot with the given preferences."""
        self._preferences = preferences
