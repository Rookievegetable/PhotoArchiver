"""Configuration infrastructure for PhotoArchiver."""

from photo_archiver.infrastructure.config.settings import (
    AppSettings,
    DEFAULT_ARCHIVE_CONFLICT_STRATEGY,
    VALID_ARCHIVE_CONFLICT_STRATEGIES,
)

__all__ = [
    "AppSettings",
    "DEFAULT_ARCHIVE_CONFLICT_STRATEGY",
    "VALID_ARCHIVE_CONFLICT_STRATEGIES",
]
