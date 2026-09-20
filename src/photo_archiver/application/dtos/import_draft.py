"""Import draft DTOs (people-import redesign stage A)."""

from dataclasses import dataclass, field
from uuid import UUID

from photo_archiver.domain.entities import ImportBatch, ImportDraftRow


@dataclass(frozen=True, slots=True)
class RawRosterTable:
    """Decoded roster file content before draft-row construction.

    ``header`` is ``None`` for headerless files; ``encoding``/``delimiter``
    record the detected parse options so the preview can show and change them.
    """

    source_type: str
    header: list[str] | None
    rows: list[list[str]]
    encoding: str
    delimiter: str | None
    sheet_name: str | None = None


@dataclass(frozen=True, slots=True)
class ImportDraft:
    """A persisted draft batch with its editable rows, ready for the preview."""

    batch: ImportBatch
    rows: list[ImportDraftRow]
    header: list[str] | None
    field_mapping: dict[str, int]
    multi_name_row_ids: tuple[UUID, ...] = field(default_factory=tuple)

    @property
    def create_count(self) -> int:
        """Rows that will create a new person."""
        return sum(1 for row in self.rows if row.action == "create")

    @property
    def merge_count(self) -> int:
        """Rows that will merge into an existing person."""
        return sum(1 for row in self.rows if row.action == "merge_existing")

    @property
    def skip_count(self) -> int:
        """Rows the user marked (or parse advised) to skip."""
        return sum(1 for row in self.rows if row.action == "skip")


@dataclass(frozen=True, slots=True)
class ImportConfirmResult:
    """Outcome of confirming one draft batch into the formal people registry."""

    imported_count: int
    merged_count: int
    skipped_count: int
    person_ids: tuple[UUID, ...]
    errors: tuple[str, ...]
