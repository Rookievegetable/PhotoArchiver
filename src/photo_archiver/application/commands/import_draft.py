"""Commands for the import-draft workflow (people-import redesign stage A)."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ParseImportDraftCommand:
    """Parse a roster file into a persisted draft batch for preview."""

    source_path: Path
    has_header: bool = True
    sheet_name: str | None = None


@dataclass(frozen=True, slots=True)
class ReparseImportDraftCommand:
    """Re-parse an existing draft batch after the user changed parse options."""

    batch_id: UUID
    source_path: Path
    has_header: bool
    sheet_name: str | None
    field_mapping: dict[str, int]


@dataclass(frozen=True, slots=True)
class ConfirmImportCommand:
    """Confirm a draft batch: atomically write people with roster order."""

    batch_id: UUID
