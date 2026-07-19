"""QSettings-backed ``UserSettingsStore`` adapter for the desktop runtime.

Persists each ``UserPreferences`` field through Qt's ``QSettings`` facility so
user overrides land in the platform-native location (Windows registry, macOS
``~/Library/Preferences/<org>/<app>.plist``, Linux ``~/.config/<org>/<app>.conf``)
without any project-owned schema or migration logic. ``QSettings`` is imported
only inside this module so CLI / CI contexts that lack PySide6 can still use
``InMemoryUserSettingsStore`` without tripping an import error.

Encoding contract:
    ``Path`` fields are serialized as ``str`` and restored through
    ``Path(str(value))`` so empty / unset stored values collapse to None.
    Threshold / workers use a ``__set__`` boolean sibling key per scalar field
    to distinguish "user never set" from "user set to the default" — this
    avoids float precision equality hazards on load (review M-3 fix).
"""

from pathlib import Path

from loguru import logger

from PySide6.QtCore import QSettings

from photo_archiver.application.dtos.settings import (
    DEFAULT_LANGUAGE,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    DEFAULT_THEME,
    UserPreferences,
)
from photo_archiver.application.ports.user_settings_store import UserSettingsStore

# QSettings group prefix keeps all preference keys under one namespace so a
# future QSettings user (e.g. window geometry) does not collide with these keys.
# Leaf keys carry a `pref_` prefix so a sibling group adding `theme` for another
# purpose (e.g. window theme) does not collide (review m-4).
_GROUP_PREFIX = "user_preferences"
_KEY_THEME = "pref_theme"
_KEY_LANGUAGE = "pref_language"
_KEY_DEFAULT_IMPORT_PATH = "pref_default_import_path"
_KEY_DEFAULT_EXPORT_PATH = "pref_default_export_path"
_KEY_MATCH_THRESHOLD = "pref_match_threshold"
_KEY_MAX_WORKERS = "pref_max_workers"
# Explicit "__set" sibling keys carry whether the user ever persisted the
# scalar field, so load can distinguish "unset → system fallback" from
# "explicitly set to default" without comparing floats for equality (review M-3).
_KEY_MATCH_THRESHOLD_SET = "pref_match_threshold__set"
_KEY_MAX_WORKERS_SET = "pref_max_workers__set"


class QSettingsUserSettingsStore(UserSettingsStore):
    """Persist ``UserPreferences`` through Qt's ``QSettings`` facility."""

    def __init__(self, settings: QSettings) -> None:
        """Initialize the adapter with a configured ``QSettings`` instance.

        Args:
            settings: Pre-built ``QSettings`` (organization / application name
                set by the caller). The adapter does NOT construct one itself
                so tests can inject an in-memory ``QSettings(format=QSettings.NativeFormat, scope=QSettings.User)``
                and so bootstrap can centralize the org/app naming policy.
        """
        self._settings = settings

    def load(self) -> UserPreferences:
        """Read persisted preferences, returning defaults for missing keys.

        Scalar fields (threshold / workers) consult their ``__set`` sibling key
        so an explicit user choice equal to the default is preserved verbatim,
        while a never-set field falls back to the dataclass default. Float
        coercion is wrapped in ``try/except`` so a corrupted registry value
        surfaces as the default rather than a ``ValueError`` (review M-4).
        """
        self._settings.beginGroup(_GROUP_PREFIX)
        try:
            theme = _str_or_default(
                self._settings.value(_KEY_THEME, defaultValue=DEFAULT_THEME, type=str),
                DEFAULT_THEME,
            )
            language = _str_or_default(
                self._settings.value(_KEY_LANGUAGE, defaultValue=DEFAULT_LANGUAGE, type=str),
                DEFAULT_LANGUAGE,
            )
            import_path_str = _str_or_default(
                self._settings.value(_KEY_DEFAULT_IMPORT_PATH, defaultValue="", type=str),
                "",
            )
            export_path_str = _str_or_default(
                self._settings.value(_KEY_DEFAULT_EXPORT_PATH, defaultValue="", type=str),
                "",
            )
            threshold = _scalar_or_default(
                self._settings,
                _KEY_MATCH_THRESHOLD,
                _KEY_MATCH_THRESHOLD_SET,
                DEFAULT_MATCH_THRESHOLD,
                float,
            )
            workers = int(
                _scalar_or_default(
                    self._settings,
                    _KEY_MAX_WORKERS,
                    _KEY_MAX_WORKERS_SET,
                    DEFAULT_MAX_WORKERS,
                    int,
                )
            )
        finally:
            self._settings.endGroup()

        return UserPreferences(
            theme=theme,
            language=language,
            default_import_path=_path_or_none(import_path_str),
            default_export_path=_path_or_none(export_path_str),
            match_threshold=threshold,
            max_workers=workers,
        )

    def save(self, preferences: UserPreferences) -> None:
        """Persist every preference field under the ``user_preferences`` group."""
        self._settings.beginGroup(_GROUP_PREFIX)
        try:
            self._settings.setValue(_KEY_THEME, preferences.theme)
            self._settings.setValue(_KEY_LANGUAGE, preferences.language)
            self._settings.setValue(
                _KEY_DEFAULT_IMPORT_PATH,
                _path_str(preferences.default_import_path),
            )
            self._settings.setValue(
                _KEY_DEFAULT_EXPORT_PATH,
                _path_str(preferences.default_export_path),
            )
            self._settings.setValue(_KEY_MATCH_THRESHOLD, float(preferences.match_threshold))
            self._settings.setValue(_KEY_MATCH_THRESHOLD_SET, True)
            self._settings.setValue(_KEY_MAX_WORKERS, int(preferences.max_workers))
            self._settings.setValue(_KEY_MAX_WORKERS_SET, True)
        finally:
            self._settings.endGroup()


def _scalar_or_default(
    settings: QSettings,
    value_key: str,
    set_key: str,
    default: float,
    cast: type,
) -> float | int:
    """Return a persisted scalar, falling back to default when unset or corrupt.

    Args:
        settings: QSettings instance already positioned inside the group.
        value_key: Scalar value storage key.
        set_key: Sibling boolean key carrying whether the user ever persisted.
        default: Fallback when ``set_key`` is falsey or the stored value fails
            to coerce (review M-4: corrupted registry entries must not crash
            load, they surface as the default with a warning).
        cast: ``float`` or ``int`` — the coercion attempted on the stored value.

    Returns:
        ``float`` when ``cast`` is float, ``int`` when ``cast`` is int. Callers
        feed the result straight into ``UserPreferences`` which accepts float
        for threshold / int for workers; the union return keeps the helper
        generic over both scalar casts without forcing a per-call cast wrapper.
    """
    if not settings.value(set_key, defaultValue=False, type=bool):
        return default
    raw = settings.value(value_key, defaultValue=default, type=cast)
    try:
        return cast(raw)
    except (TypeError, ValueError):
        logger.warning(
            "QSettings preference {} corrupt ({!r}); falling back to default {}",
            value_key,
            raw,
            default,
        )
        return default


def _path_or_none(value: str) -> Path | None:
    """Restore a stored path string to ``Path``, collapsing empty to None."""
    if value is None or str(value).strip() == "":
        return None
    return Path(str(value))


def _path_str(path: Path | None) -> str:
    """Serialize a ``Path | None`` for ``QSettings`` storage."""
    return str(path) if path is not None else ""


def _str_or_default(value: object, default: str) -> str:
    """Coerce a QSettings.value() object return into a str, falling back on default.

    ``QSettings.value`` is typed to return ``object`` regardless of the ``type``
    keyword argument, so we normalize here rather than at every call site.
    """
    if value is None:
        return default
    text = str(value)
    return text if text != "" else default
