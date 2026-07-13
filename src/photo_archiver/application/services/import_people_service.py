"""Service implementation for importing people."""

from photo_archiver.application.commands import ImportPeopleCommand
from photo_archiver.application.dtos import ImportPeopleResult, PersonImportRow
from photo_archiver.application.ports import PersonImportReader
from photo_archiver.application.use_cases import ImportPeopleUseCase
from photo_archiver.domain import Person, PersonIdentity, PersonRepository


class ImportPeopleService(ImportPeopleUseCase):
    """Import people using a reader port and a person repository."""

    def __init__(self, reader: PersonImportReader, repository: PersonRepository) -> None:
        """Initialize the service with its required ports."""
        self._reader = reader
        self._repository = repository

    def execute(self, command: ImportPeopleCommand) -> ImportPeopleResult:
        """Import normalized person rows into the repository."""
        rows = self._reader.read(
            command.source_path,
            has_header=command.has_header,
            sheet_name=command.sheet_name,
        )
        imported_ids = []
        errors = []
        skipped_count = 0

        for row in rows:
            try:
                identity = self._build_identity(row)
                if identity is not None and self._repository.find_by_identity(identity) is not None:
                    skipped_count += 1
                    continue

                person = Person(
                    name=row.name,
                    identity=identity,
                    department=row.department,
                    note=row.note,
                )
                self._repository.add(person)
                imported_ids.append(person.id)
            except Exception as exc:  # noqa: BLE001 - keep row-level import resilient.
                errors.append(self._format_row_error(row, exc))

        return ImportPeopleResult(
            imported_count=len(imported_ids),
            skipped_count=skipped_count,
            person_ids=tuple(imported_ids),
            errors=tuple(errors),
        )

    @staticmethod
    def _build_identity(row: PersonImportRow) -> PersonIdentity | None:
        """Build an optional identity value object from an import row."""
        if row.identity is None or not row.identity.strip():
            return None
        return PersonIdentity(row.identity)

    @staticmethod
    def _format_row_error(row: PersonImportRow, exc: Exception) -> str:
        """Format a row-level import error for presentation layers."""
        location = f"row {row.row_number}" if row.row_number is not None else "unknown row"
        return f"{location}: {exc}"