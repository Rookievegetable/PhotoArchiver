"""SettingsService — load/save user preferences with system-default fallback.

Coordinate ``UserSettingsStore`` (persistence) + ``SystemSettings`` (read-only
fallback for fields the user has never overridden). ``load`` merges store
values with system defaults; ``save`` validates the candidate before
persisting so invalid input can never land on disk.

This service does NOT know about QSettings, JSON, or DB — those technologies
live behind the ``UserSettingsStore`` port in the infrastructure layer.
"""

from loguru import logger

from photo_archiver.application.dtos.settings import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    UserPreferences,
    validate_preferences,
)
from photo_archiver.application.ports.system_settings import SystemSettings
from photo_archiver.application.ports.user_settings_store import UserSettingsStore
from photo_archiver.application.use_cases.settings import SettingsUseCase


class SettingsService(SettingsUseCase):
    """Coordinate user-preference persistence with system-level fallback defaults."""

    def __init__(
        self,
        user_settings_store: UserSettingsStore,
        system_settings: SystemSettings | None = None,
    ) -> None:
        """Initialize the service with its persistence port and optional system fallback.

        Args:
            user_settings_store: Where the user's overrides are read from / written to.
            system_settings: Read-only system-level defaults used when the store has
                never persisted a value. When None the service falls back to the
                ``UserPreferences`` dataclass defaults (which mirror AppSettings).
        """
        self._user_settings_store = user_settings_store
        self._system_settings = system_settings

    def rebind_store(
        self,
        user_settings_store: UserSettingsStore,
        system_settings: SystemSettings | None = None,
    ) -> None:
        """Swap the persistence store and optional system fallback at runtime.

        Used by ``app/ui_assembly.build_ui_controllers`` to replace the bootstrap
        ``InMemoryUserSettingsStore`` with a ``QSettingsUserSettingsStore`` once
        the Qt runtime is available, without forcing callers that already
        captured ``services.settings`` to re-fetch the reference. Exposing this
        as a public method keeps the app → application dependency at the Protocol
        boundary (DEP-012/DEP-013) rather than reaching into private fields.

        Args:
            user_settings_store: Replacement persistence port.
            system_settings: Optional replacement system-level fallback; when
                None the existing system fallback (if any) is preserved.
        """
        self._user_settings_store = user_settings_store
        if system_settings is not None:
            self._system_settings = system_settings

    def load(self) -> UserPreferences:
        """Return the persisted user preferences, falling back to system defaults.

        For threshold / workers the service overrides the dataclass-default
        value with the system-level default ONLY when the user never set it
        (detected via equality with the dataclass default — these defaults are
        sentinel integers / 2-decimal floats not subject to precision drift).
        Theme / language / paths have no system-level equivalent and always
        come from the store.
        """
        persisted = self._user_settings_store.load()
        if self._system_settings is None:
            return persisted
        effective_threshold = (
            self._system_settings.match_threshold
            if persisted.match_threshold == DEFAULT_MATCH_THRESHOLD
            else persisted.match_threshold
        )
        effective_workers = (
            self._system_settings.max_workers
            if persisted.max_workers == DEFAULT_MAX_WORKERS
            else persisted.max_workers
        )
        return UserPreferences(
            theme=persisted.theme,
            language=persisted.language,
            default_import_path=persisted.default_import_path,
            default_export_path=persisted.default_export_path,
            match_threshold=effective_threshold,
            max_workers=effective_workers,
        )

    def save(self, preferences: UserPreferences) -> None:
        """Validate then persist the given user preferences.

        Args:
            preferences: Candidate preferences value object.

        Raises:
            InvalidPreferencesError: When any field violates its bound. The
                store is not touched in that case so persisted state stays honest.
        """
        validate_preferences(preferences)
        self._user_settings_store.save(preferences)
        # Log field count rather than values — future UserPreferences fields may
        # carry secrets (review m-1: do not dump values unconditionally).
        logger.info("User preferences saved (6 fields)")
