"""Confirm an import draft batch — atomically write people with roster order.

Stage A (owner plan §3.1/§4.2): confirmation is the only point where draft
rows touch the formal registry. Actions:

- ``create``          → new ``Person`` with ``roster_order``/``source_batch_id``;
- ``merge_existing``  → attach the roster position to the referenced person;
- ``skip``            → left untouched.

A DB duplicate discovered at confirm time (TOCTOU second line) degrades to a
merge, never a hard failure; row-level validation errors are isolated with
row numbers. The whole batch runs in one unit of work. The roster sequence
continues from the registry's global maximum (owner ruling on LIMIT-007), so
order is stable and monotonic across batches.
"""

from datetime import datetime
from uuid import UUID

from loguru import logger

from photo_archiver.application.commands.import_draft import ConfirmImportCommand
from photo_archiver.application.dtos.import_draft import ImportConfirmResult
from photo_archiver.application.ports import UnitOfWork
from photo_archiver.domain.entities import (
    BATCH_STATUS_CONFIRMED,
    DRAFT_ACTION_MERGE_EXISTING,
    DRAFT_ACTION_SKIP,
)
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories import ImportBatchRepository, PersonRepository
from photo_archiver.domain.value_objects import PersonIdentity


class ConfirmImportService:
    """Confirm one draft batch: write people inside a single transaction."""

    def __init__(
        self,
        import_batches: ImportBatchRepository,
        people: PersonRepository,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Initialize with the batch/people repositories and optional UoW."""
        self._import_batches = import_batches
        self._people = people
        self._unit_of_work = unit_of_work

    def execute(self, command: ConfirmImportCommand) -> ImportConfirmResult:
        """Confirm the batch; draft rows become people (or merges/skips)."""
        batch = self._import_batches.get_batch(command.batch_id)
        if batch is None:
            raise ValueError(f"import batch not found: {command.batch_id}")
        rows = sorted(
            self._import_batches.list_draft_rows(command.batch_id),
            key=lambda row: row.order_index,
        )

        imported_ids: list[UUID] = []
        errors: list[str] = []
        merged_count = 0
        skipped_count = 0
        # Owner ruling (LIMIT-007 / acceptance F-A1): continue the roster order
        # from the global maximum instead of restarting at 1 per batch, so the
        # sequence is globally monotonic and stable across batches.
        order_base = self._people.max_roster_order() or 0

        def _run_batch() -> None:
            nonlocal merged_count, skipped_count
            order_seq = order_base
            for row in rows:
                order_seq += 1
                if row.action == DRAFT_ACTION_SKIP:
                    skipped_count += 1
                    continue
                try:
                    if row.action == DRAFT_ACTION_MERGE_EXISTING:
                        self._merge_row(row, order_seq, command.batch_id)
                        merged_count += 1
                        continue
                    person_id = self._create_row(row, order_seq, command.batch_id)
                    if person_id is None:
                        merged_count += 1  # DB duplicate degraded to a merge
                        continue
                    imported_ids.append(person_id)
                except (ValueError, ValidationError) as exc:
                    errors.append(f"row {row.source_row}: {exc}")

        if self._unit_of_work is not None:
            with self._unit_of_work:
                _run_batch()
        else:
            _run_batch()

        self._import_batches.set_batch_status(
            command.batch_id, BATCH_STATUS_CONFIRMED, confirmed_at=datetime.now(),
        )
        logger.info(
            "Import batch {} confirmed: imported={} merged={} skipped={} errors={}",
            command.batch_id, len(imported_ids), merged_count, skipped_count, len(errors),
        )
        return ImportConfirmResult(
            imported_count=len(imported_ids),
            merged_count=merged_count,
            skipped_count=skipped_count,
            person_ids=tuple(imported_ids),
            errors=tuple(errors),
        )

    def _create_row(self, row, order_seq: int, batch_id: UUID) -> UUID | None:  # noqa: ANN001
        """Create a person from a ``create`` row; degrade DB duplicates to merge."""
        identity = PersonIdentity(row.parsed_identity) if row.parsed_identity else None
        if identity is not None:
            existing = self._people.find_by_identity(identity)
            if existing is not None:
                self._attach_roster(existing, order_seq, batch_id)
                return None
        person = Person(
            name=row.parsed_name,
            identity=identity,
            department=row.parsed_department,
            note=row.parsed_note,
            roster_order=order_seq,
            source_batch_id=batch_id,
        )
        self._people.add(person)
        return person.id  # type: ignore[return-value]  # Person.__post_init__ guarantees non-None

    def _merge_row(self, row, order_seq: int, batch_id: UUID) -> None:  # noqa: ANN001
        """Attach the roster position to the referenced (or looked-up) person."""
        target = None
        if row.merge_target_id is not None:
            target = self._people.find_by_id(row.merge_target_id)
        if target is None and row.parsed_identity:
            target = self._people.find_by_identity(PersonIdentity(row.parsed_identity))
        if target is None and row.parsed_name:
            target = self._people.find_by_name_department(
                row.parsed_name.strip(), row.parsed_department,
            )
        if target is None:
            raise ValidationError(
                f"merge target not found for row {row.source_row} ({row.parsed_name})",
            )
        self._attach_roster(target, order_seq, batch_id)

    def _attach_roster(self, person: Person, order_seq: int, batch_id: UUID) -> None:
        """Update an existing person's roster position and source batch."""
        person.roster_order = order_seq
        person.source_batch_id = batch_id
        self._people.add(person)
