"""Archive command — request archiving approved photos."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ArchivePhotosCommand:
    """Request archiving photos approved for one or more persons.

    Args:
        archive_root: Root directory of the archive tree. Overrides
            AppSettings.archive_root when provided (CLI --archive-root flag).
        person_ids: Persons whose APPROVED photos to archive; empty tuple
            means "all persons with approved photos".
        photo_ids: Specific photos to archive (B3 批量归档); empty tuple means
            "use person_ids selection". When non-empty, planner filters the
            APPROVED recognition set to these photos only — letting the UI hand
            the user's multi-select straight through without rescanning.
            Backward compatible: legacy callers leave it unset (default empty).
        conflict_strategy: How to handle existing target files:
            skip | overwrite | rename. None means use settings default.
        dry_run: When True, log intended operations without touching the
            filesystem (落裁决 #3 验收条目). Records still persist as DRY_RUN.
    """

    archive_root: Path
    person_ids: tuple[UUID, ...] = ()
    photo_ids: tuple[UUID, ...] = ()
    conflict_strategy: str | None = None
    dry_run: bool = False
