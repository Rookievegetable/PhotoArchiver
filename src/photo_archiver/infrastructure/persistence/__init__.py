"""Infrastructure persistence adapters for user preferences.

Subpackage boundary: ``infrastructure/persistence/`` is the home for adapters
that translate between the Application-layer ``UserSettingsStore`` port and
specific persistence technologies (QSettings for desktop runtime, in-memory
for tests/CLI/CI environments where PySide6 is not importable).
"""

from photo_archiver.infrastructure.persistence.in_memory_user_settings_store import (
    InMemoryUserSettingsStore,
)

__all__ = [
    "InMemoryUserSettingsStore",
]
