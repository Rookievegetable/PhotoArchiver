"""Service implementation for importing people."""

from collections.abc import Sequence

from photo_archiver.application.commands import ImportPeopleCommand
from photo_archiver.application.dtos import ImportPeopleResult, PersonImportRow
from photo_archiver.application.ports import PersonImportReader, UnitOfWork
from photo_archiver.application.use_cases import ImportPeopleUseCase
from photo_archiver.domain import Person, PersonIdentity, PersonRepository
from photo_archiver.domain.exceptions import ValidationError

# P0-7 (Phase B, D-B7 批复默认值)：按批原子导入的批量大小。
BATCH_SIZE = 500


class ImportPeopleService(ImportPeopleUseCase):
    """Import people using a reader port and a person repository."""

    def __init__(
        self,
        reader: PersonImportReader,
        repository: PersonRepository,
        unit_of_work: UnitOfWork | None = None,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        """Initialize the service with its required ports.

        Args:
            reader: File reader port (unused by the plugin ``import_rows`` path).
            repository: Persistence target for person entities.
            unit_of_work: Optional transactional scope (P0-7, D-B1 按批原子).
                When provided, rows persist in atomic batches of ``batch_size``:
                an unexpected failure mid-batch rolls back only the current
                batch while previously committed batches stay durable. When
                ``None`` (in-memory unit-test path, mirroring the optional-UoW
                convention of ``ReviewRecognitionService``) rows persist bare.
            batch_size: Rows per atomic batch (D-B7 default 500).
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._reader = reader
        self._repository = repository
        self._unit_of_work = unit_of_work
        self._batch_size = batch_size

    def execute(self, command: ImportPeopleCommand) -> ImportPeopleResult:
        """Import normalized person rows into the repository."""
        rows = self._reader.read(
            command.source_path,
            has_header=command.has_header,
            sheet_name=command.sheet_name,
        )
        return self.import_rows(rows)

    def import_rows(self, rows: Sequence[PersonImportRow]) -> ImportPeopleResult:
        """Import pre-parsed person rows into the repository (ADR-028 plugin path).

        ``PluginContextService.import_people`` maps Plugin DTOs onto this entry
        point so plugins can write person entities without touching a file
        reader or the ``PersonRepository`` directly (DEP-060 guard) — batching
        and dedupe below therefore cover both the file and plugin paths.

        P0-7 (Phase B, D-B1 按批原子)：rows are chunked into batches of
        ``batch_size``; each batch persists inside one unit-of-work scope so a
        crash mid-import leaves at most fully committed batches behind — never
        a half-batch. Row-level problems (invalid values, D-B2 duplicates) are
        isolated: they are recorded in ``errors`` / counted as ``skipped`` and
        never abort the batch. An unexpected (non-row-level) failure rolls back
        the current batch and propagates; earlier batches stay committed.

        P0-7 (D-B2 无 identity 查重)：rows without an identity are deduplicated
        by exact normalized name + department, mirroring the identity lookup.

        Args:
            rows: Normalized person rows; callers should fill ``row_number``
                so row-level errors stay attributable.

        Returns:
            Aggregate outcome with imported/skipped counts, imported ids,
            and one error message per failed row.
        """
        imported_ids = []
        errors = []
        skipped_count = 0

        for batch in self._chunk_rows(rows):
            if self._unit_of_work is not None:
                with self._unit_of_work:
                    batch_ids, batch_errors, batch_skipped = self._import_batch(batch)
            else:
                batch_ids, batch_errors, batch_skipped = self._import_batch(batch)
            imported_ids.extend(batch_ids)
            errors.extend(batch_errors)
            skipped_count += batch_skipped

        return ImportPeopleResult(
            imported_count=len(imported_ids),
            skipped_count=skipped_count,
            person_ids=tuple(imported_ids),  # type: ignore[arg-type]  # Person.__post_init__ guarantees ids are set
            errors=tuple(errors),
        )

    def _chunk_rows(self, rows: Sequence[PersonImportRow]) -> list[list[PersonImportRow]]:
        """Split rows into atomic batches of ``batch_size`` rows."""
        return [
            list(rows[index : index + self._batch_size])
            for index in range(0, len(rows), self._batch_size)
        ]

    def _import_batch(
        self,
        batch: list[PersonImportRow],
    ) -> tuple[list, list[str], int]:
        """Persist one batch of rows, isolating row-level failures.

        Returns:
            Imported person ids, row error messages, and the skipped count.
        """
        imported_ids = []
        errors = []
        skipped_count = 0

        for row in batch:
            try:
                identity = self._build_identity(row)
                if identity is not None:
                    if self._repository.find_by_identity(identity) is not None:
                        skipped_count += 1
                        continue
                elif self._is_name_department_duplicate(row):
                    skipped_count += 1
                    continue

                person = Person(
                    name=row.name,
                    identity=identity,
                    department=row.department,
                    note=row.note,
                )
                self._repository.add(person)
                imported_ids.append(person.id)  # type: ignore[arg-type]  # Person.__post_init__ guarantees id is set
            except (ValueError, ValidationError) as exc:  # noqa: BLE001 - keep row-level import resilient.
                errors.append(self._format_row_error(row, exc))

        return imported_ids, errors, skipped_count

    def _is_name_department_duplicate(self, row: PersonImportRow) -> bool:
        """Return whether an identity-less row duplicates an existing person.

        Normalization mirrors ``Person.__post_init__`` so the lookup compares
        against exactly the values persisted by ``add`` (P0-7, D-B2).
        """
        return (
            self._repository.find_by_name_department(
                row.name.strip(),
                self._normalize_department(row),
            )
            is not None
        )

    @staticmethod
    def _normalize_department(row: PersonImportRow) -> str | None:
        """Normalize a row department the same way ``Person`` persists it."""
        if row.department is None:
            return None
        return row.department.strip() or None

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