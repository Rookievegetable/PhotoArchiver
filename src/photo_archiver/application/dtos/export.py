"""DTOs for the Step 14 Export workflow.

Defines the export scope enum and the aggregate ``ExportData`` DTO the
application layer assembles before handing it to an infrastructure exporter.
"""

from dataclasses import dataclass, field
from enum import Enum


class ExportScope(str, Enum):
    """Defines which data to include in an export.

    Inheriting from ``str`` keeps the enum serializable for CLI / configuration
    without extra adapters, following the convention from ``MatchStatus`` and
    ``ArchiveStatus``.
    """

    ALL = "all"                     # All photos, people, results, archive records
    CURRENT_BATCH = "current_batch" # The most recently processed batch
    FILTERED = "filtered"           # A subset filtered by the caller


@dataclass(frozen=True, slots=True)
class ExportPersonRow:
    """One row of person data for the export."""

    person_id: str
    name: str
    department: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ExportPhotoRow:
    """One row of photo data for the export."""

    photo_id: str
    path: str
    original_name: str | None = None
    folder_name: str = ""
    captured_at: str = ""
    registered_at: str = ""


@dataclass(frozen=True, slots=True)
class ExportMatchRow:
    """One row of recognition/match data for the export."""

    photo_id: str
    person_id: str
    person_name: str
    confidence: float
    status: str  # pending / approved / rejected


@dataclass(frozen=True, slots=True)
class ExportArchiveRow:
    """One row of archive record data for the export."""

    photo_id: str
    person_name: str
    target_path: str
    status: str
    archived_at: str = ""


@dataclass(frozen=True, slots=True)
class ExportData:
    """Aggregate DTO containing all data the application layer gathered for export.

    The ``ExportService`` assembles this from its repository sources before
    passing it to a concrete :class:`~photo_archiver.infrastructure.exporters.Exporter`.
    """

    people: tuple[ExportPersonRow, ...] = field(default_factory=tuple)
    photos: tuple[ExportPhotoRow, ...] = field(default_factory=tuple)
    matches: tuple[ExportMatchRow, ...] = field(default_factory=tuple)
    archive_records: tuple[ExportArchiveRow, ...] = field(default_factory=tuple)

    @property
    def total_row_count(self) -> int:
        """Return the total number of data rows assembled."""
        return len(self.people) + len(self.photos) + len(self.matches) + len(self.archive_records)
