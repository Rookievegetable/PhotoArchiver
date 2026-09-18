"""Read-only workspace readiness snapshot."""

from dataclasses import dataclass
from enum import StrEnum


class ModelAvailability(StrEnum):
    """Readiness of the assembled recognition pipeline, not just files on disk."""

    AVAILABLE = "available"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WorkspaceStatus:
    """Library counts and environment facts used by workspace action policy."""

    has_persons: bool
    has_photos: bool
    pending_match_count: int
    pending_review_count: int
    archivable_count: int
    archive_root_available: bool
    model_availability: ModelAvailability
