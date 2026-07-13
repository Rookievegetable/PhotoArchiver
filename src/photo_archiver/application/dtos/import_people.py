"""DTOs for people import workflows."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PersonImportRow:
    """Normalized person data read from an import source."""

    name: str
    identity: str | None = None
    department: str | None = None
    note: str | None = None
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class ImportPeopleResult:
    """Outcome of a people import use case."""

    imported_count: int = 0
    skipped_count: int = 0
    person_ids: tuple[UUID, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        """Return whether the import completed without row-level errors."""
        return not self.errors