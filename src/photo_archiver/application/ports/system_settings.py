"""Port for read-only system configuration used by application services."""

from typing import Protocol


class SystemSettings(Protocol):
    """Provide read-only access to system-level configuration values.

    ``AppSettings`` from the infrastructure layer implements this protocol so
    that application services can fall back to system defaults when a user
    preference has not been overridden.
    """

    @property
    def match_threshold(self) -> float:
        """Return the default matching confidence threshold."""
        ...

    @property
    def max_workers(self) -> int:
        """Return the default worker concurrency cap."""
        ...
