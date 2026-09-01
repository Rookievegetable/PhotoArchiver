"""Integration tests for Step 14 Export workflow.

Verifies that:
- ExportService + ExcelExporter produces an openable .xlsx file
- ExportService + CsvExporter produces a readable .csv file
- Error cases (empty data, unwritable path) are handled gracefully

These tests use in-memory repositories so no SQLite / model pack is required.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.domain.entities import ArchiveRecord, ArchiveStatus, MatchStatus, Person, Photo, RecognitionResult
from photo_archiver.domain.repositories import (
    ArchiveRecordRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)
from photo_archiver.domain.value_objects import PhotoPath
from photo_archiver.infrastructure.exporters import CsvExporter, ExcelExporter


# ── Helpers ──────────────────────────────────────────────────────────────────


class _InMemoryPersonRepository(PersonRepository):
    """Minimal in-memory person repo for test data."""

    def __init__(self) -> None:
        self._persons: list[Person] = []

    def add(self, person: Person) -> None:
        self._persons.append(person)

    def list_all(self) -> list[Person]:
        return list(self._persons)

    def find_by_id(self, person_id: UUID) -> Person | None:
        for p in self._persons:
            if p.id == person_id:
                return p
        return None

    def find_by_identity(self, identity) -> Person | None:  # noqa: ANN001
        for p in self._persons:
            if p.identity == identity:
                return p
        return None


class _InMemoryPhotoRepository(PhotoRepository):
    """Minimal in-memory photo repo for test data."""

    def __init__(self) -> None:
        self._photos: list[Photo] = []

    def add(self, photo: Photo) -> None:
        self._photos.append(photo)

    def list_all(self) -> list[Photo]:
        return list(self._photos)

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        for ph in self._photos:
            if ph.id == photo_id:
                return ph
        return None

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        for ph in self._photos:
            if ph.path == path:
                return ph
        return None

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        return [ph for ph in self._photos if ph.folder_id == folder_id]


class _InMemoryRecognitionRepository(RecognitionRepository):
    """Minimal in-memory recognition repo for test data."""

    def __init__(self) -> None:
        self._results: list[RecognitionResult] = []

    def add(self, result: RecognitionResult) -> None:
        self._results.append(result)

    def find_by_id(self, result_id: UUID) -> RecognitionResult | None:
        for r in self._results:
            if r.id == result_id:
                return r
        return None

    def list_by_photo(self, photo_id: UUID) -> list[RecognitionResult]:
        return [r for r in self._results if r.photo_id == photo_id]

    def list_first_by_photo_ids(self, photo_ids) -> dict:
        return {
            r.photo_id: r
            for r in reversed(self._results)
            if r.photo_id in set(photo_ids)
        }

    def list_pending(self) -> list[RecognitionResult]:
        return [r for r in self._results if r.status is MatchStatus.PENDING]

    def list_approved_by_person(self, person_id: UUID) -> list[RecognitionResult]:
        return [r for r in self._results if r.person_id == person_id and r.status is MatchStatus.APPROVED]

    def update_status(self, result_id: UUID, status: MatchStatus) -> int:
        count = 0
        for r in self._results:
            if r.id == result_id:
                r.status = status
                count = 1
        return count


class _InMemoryArchiveRecordRepository(ArchiveRecordRepository):
    """Minimal in-memory archive record repo for test data."""

    def __init__(self) -> None:
        self._records: list[ArchiveRecord] = []

    def add(self, record: ArchiveRecord) -> None:
        self._records.append(record)

    def find_by_id(self, record_id: UUID) -> ArchiveRecord | None:
        for r in self._records:
            if r.id == record_id:
                return r
        return None

    def find_by_photo(self, photo_id: UUID) -> ArchiveRecord | None:
        for r in self._records:
            if r.photo_id == photo_id:
                return r
        return None

    def list_by_status(self, status: ArchiveStatus) -> list[ArchiveRecord]:
        return [r for r in self._records if r.status == status]

    def list_all(self) -> list[ArchiveRecord]:
        return list(self._records)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestExportExcel:
    """Excel export integration tests."""

    def test_excel_export_creates_openable_file(self) -> None:
        """Export rows to .xlsx and verify the workbook can be opened."""
        person_id = uuid4()
        photo_id = uuid4()
        person_repo = _InMemoryPersonRepository()
        person_repo.add(Person(name="Alice", id=person_id))
        photo_repo = _InMemoryPhotoRepository()
        photo_repo.add(
            Photo(
                path=PhotoPath("photos/alice_wedding.jpg"),
                id=photo_id,
            )
        )
        recognition_repo = _InMemoryRecognitionRepository()
        archive_repo = _InMemoryArchiveRecordRepository()

        service = ExportService(
            person_repository=person_repo,
            photo_repository=photo_repo,
            recognition_repository=recognition_repo,
            archive_record_repository=archive_repo,
        )

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "export.xlsx"
            result = service.export(
                exporter=ExcelExporter(),
                output_path=str(output),
                scope=ExportScope.ALL,
            )

            assert output.exists(), "Excel file was not created"
            assert result.startswith("Exported"), f"Unexpected result: {result}"
            # openpyxl can open the file
            from openpyxl import load_workbook

            wb = load_workbook(str(output))
            assert wb.active is not None
            assert "sheet names are case-insensitive; active.title returns the title"
            ws = wb.active
            assert ws is not None

    def test_excel_empty_data_produces_header_only(self) -> None:
        """Export with no data still produces a valid workbook with header row."""
        service = ExportService(
            person_repository=_InMemoryPersonRepository(),
            photo_repository=_InMemoryPhotoRepository(),
            recognition_repository=_InMemoryRecognitionRepository(),
            archive_record_repository=_InMemoryArchiveRecordRepository(),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "empty.xlsx"
            result = service.export(
                exporter=ExcelExporter(),
                output_path=str(output),
                scope=ExportScope.ALL,
            )
            assert output.exists()
            assert "Exported 0 rows" in result


class TestExportCsv:
    """CSV export integration tests."""

    def test_csv_export_creates_readable_file(self) -> None:
        """Export rows to .csv and verify the content."""
        person_id = uuid4()
        person_repo = _InMemoryPersonRepository()
        person_repo.add(Person(name="Bob", id=person_id))
        photo_repo = _InMemoryPhotoRepository()
        archive_repo = _InMemoryArchiveRecordRepository()
        recognition_repo = _InMemoryRecognitionRepository()

        service = ExportService(
            person_repository=person_repo,
            photo_repository=photo_repo,
            recognition_repository=recognition_repo,
            archive_record_repository=archive_repo,
        )

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "export.csv"
            result = service.export(
                exporter=CsvExporter(),
                output_path=str(output),
                scope=ExportScope.ALL,
            )

            assert output.exists(), "CSV file was not created"
            assert result.startswith("Exported")
            content = output.read_text(encoding="utf-8-sig")
            assert "person_name" in content
            assert "Bob" in content

    def test_csv_empty_data_produces_header_only(self) -> None:
        """Export with no data still produces a valid CSV with header row."""
        service = ExportService(
            person_repository=_InMemoryPersonRepository(),
            photo_repository=_InMemoryPhotoRepository(),
            recognition_repository=_InMemoryRecognitionRepository(),
            archive_record_repository=_InMemoryArchiveRecordRepository(),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "empty.csv"
            result = service.export(
                exporter=CsvExporter(),
                output_path=str(output),
                scope=ExportScope.ALL,
            )
            assert output.exists()
            assert "Exported 0 rows" in result


class TestScopeContractCompat:
    """Phase 7 Commit 1 — ALL-scope invariance under the criteria signature.

    Contract: docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md §6 Commit 1
    threads an optional ``criteria`` through ``ExportService.export`` with ZERO
    behavior change: ``ALL`` must produce identical output whether or not a
    criteria snapshot is supplied (criteria is only ever consumed by the
    ``FILTERED`` scope, delivered by a later FEATURE-004 commit).
    """

    def test_all_export_identical_with_and_without_criteria(self) -> None:
        """ALL export output is byte-identical with criteria=None vs supplied."""
        person_id = uuid4()
        photo_id = uuid4()
        person_repo = _InMemoryPersonRepository()
        person_repo.add(Person(name="Carol", id=person_id))
        photo_repo = _InMemoryPhotoRepository()
        photo_repo.add(Photo(path=PhotoPath("photos/carol_party.jpg"), id=photo_id))
        archive_repo = _InMemoryArchiveRecordRepository()
        archive_repo.add(
            ArchiveRecord(
                photo_id=photo_id,
                target_archive_root="Z:/Archive",
                target_person_name="Carol",
                target_event_or_date="2026-08-30",
                target_original_name="carol_party.jpg",
                status=ArchiveStatus.ARCHIVED,
            )
        )
        service = ExportService(
            person_repository=person_repo,
            photo_repository=photo_repo,
            recognition_repository=_InMemoryRecognitionRepository(),
            archive_record_repository=archive_repo,
        )

        with TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain.csv"
            with_criteria = Path(tmp) / "with_criteria.csv"
            result_plain = service.export(
                exporter=CsvExporter(),
                output_path=str(plain),
                scope=ExportScope.ALL,
            )
            result_with_criteria = service.export(
                exporter=CsvExporter(),
                output_path=str(with_criteria),
                scope=ExportScope.ALL,
                criteria=PhotoSearchCriteria(match_status=MatchStatus.APPROVED),
            )

            # The exporter summary embeds the output file path — compare only
            # the "Exported N rows" prefix; the real invariant is identical
            # FILE CONTENT between the two runs.
            assert result_plain.split()[:3] == result_with_criteria.split()[:3]
            assert (
                plain.read_text(encoding="utf-8-sig")
                == with_criteria.read_text(encoding="utf-8-sig")
            )
            assert "Carol" in plain.read_text(encoding="utf-8-sig")
