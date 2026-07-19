"""Data transfer objects for user preferences and settings."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_THEME = "system"
VALID_THEMES = ("system", "light", "dark")

DEFAULT_LANGUAGE = "system"
VALID_LANGUAGES = ("system", "zh", "en")

DEFAULT_MATCH_THRESHOLD = 0.40
MIN_MATCH_THRESHOLD = 0.0
MAX_MATCH_THRESHOLD = 1.0

DEFAULT_MAX_WORKERS = 4
MIN_MAX_WORKERS = 1
MAX_MAX_WORKERS = 32


@dataclass(frozen=True)
class UserPreferences:
    """User-facing preferences persisted independently of system configuration.

    System configuration (``AppSettings``) is loaded from environment variables
    and ``.env`` at startup and is treated as read-only at runtime. This value
    object holds per-user choices that can be changed from the UI and persisted
    through ``UserSettingsStore``.

    Validation lives in :func:`validate_preferences` rather than ``__post_init__``
    so a service can collect all field violations before raising and so tests
    can construct partially-overridden instances without tripping the bounds.
    """

    theme: str = DEFAULT_THEME
    language: str = DEFAULT_LANGUAGE
    default_import_path: Path | None = None
    default_export_path: Path | None = None
    match_threshold: float = DEFAULT_MATCH_THRESHOLD
    max_workers: int = DEFAULT_MAX_WORKERS


class InvalidPreferencesError(ValueError):
    """Raised when one or more UserPreferences fields fall outside accepted bounds."""


def _validate_path(field_name: str, path: Path | None) -> list[str]:
    """Reject relative parent-traversal in a path field (review m-2: path safety).

    None (unset) is always accepted per the contract that ``None`` means "user
    never picked one". An existing absolute or relative path is accepted; only
    a ``..`` segment that would traverse above the working directory is rejected
    to keep an accidental paste of ``../../etc`` from being persisted.
    """
    if path is None:
        return []
    if path.is_absolute():
        return []
    if ".." in path.parts:
        return [f"{field_name} {path} contains parent-traversal '..'"]
    return []


def validate_preferences(preferences: UserPreferences) -> None:
    """Validate every preference field, raising with a combined message on failure.

    Args:
        preferences: The candidate preferences value object.

    Raises:
        InvalidPreferencesError: When any field violates its acceptance bound.
            The message lists every offending field so the UI can surface all
            issues at once rather than forcing the user to fix-and-resubmit.
    """
    violations: list[str] = []
    if preferences.theme not in VALID_THEMES:
        violations.append(f"theme {preferences.theme!r} not in {VALID_THEMES}")
    if preferences.language not in VALID_LANGUAGES:
        violations.append(f"language {preferences.language!r} not in {VALID_LANGUAGES}")
    if not MIN_MATCH_THRESHOLD <= preferences.match_threshold <= MAX_MATCH_THRESHOLD:
        violations.append(
            f"match_threshold {preferences.match_threshold} outside "
            f"[{MIN_MATCH_THRESHOLD}, {MAX_MATCH_THRESHOLD}]"
        )
    if not MIN_MAX_WORKERS <= preferences.max_workers <= MAX_MAX_WORKERS:
        violations.append(
            f"max_workers {preferences.max_workers} outside "
            f"[{MIN_MAX_WORKERS}, {MAX_MAX_WORKERS}]"
        )
    violations.extend(_validate_path("default_import_path", preferences.default_import_path))
    violations.extend(_validate_path("default_export_path", preferences.default_export_path))
    if violations:
        raise InvalidPreferencesError("; ".join(violations))
