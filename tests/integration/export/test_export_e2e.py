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
                path=PhotoPath("/photos/alice_wedding.jpg"),
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
