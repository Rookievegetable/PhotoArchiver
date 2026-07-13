"""Application service workflow tests using infrastructure test adapters."""

from pathlib import Path

import pytest

from photo_archiver.application import (
    ImportPeopleCommand,
    ImportPeopleService,
    RegisterPhotoCommand,
    RegisterPhotoService,
    ScanAndRegisterPhotosCommand,
    ScanAndRegisterPhotosService,
    ScanPhotoFolderCommand,
    ScanPhotoFolderService,
)
from photo_archiver.application.dtos import PersonImportRow
from photo_archiver.domain import PhotoMetadata
from photo_archiver.infrastructure import (
    InMemoryFolderRepository,
    InMemoryPersonRepository,
    InMemoryPhotoRepository,
    LocalPhotoFileScanner,
    TxtPersonImportReader,
)


class FailingPhotoFileScanner:
    """Scanner test double that raises a configured exception."""

    def __init__(self, exception: Exception) -> None:
        """Store the exception raised by scan."""
        self._exception = exception

    def scan(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201 - protocol test double.
        """Raise the configured exception."""
        raise self._exception


class RecordingPersonImportReader:
    """Person import reader test double that records call arguments."""

    def __init__(self) -> None:
        """Initialize recorded call values."""
        self.source_path: Path | None = None
        self.has_header: bool | None = None
        self.sheet_name: str | None = None

    def read(
        self,
        source_path: Path,
        *,
        has_header: bool = True,
        sheet_name: str | None = None,
    ) -> list[PersonImportRow]:
        """Record arguments and return one valid import row."""
        self.source_path = source_path
        self.has_header = has_header
        self.sheet_name = sheet_name
        return [PersonImportRow(name="Alice", identity="A001")]


class SelectiveFailingMetadataReader:
    """Metadata reader test double that fails for configured file names."""

    def __init__(self, failing_names: set[str] | None = None) -> None:
        """Store file names that should fail metadata reads."""
        self._failing_names = failing_names or set()

    def read(self, path: Path) -> PhotoMetadata:
        """Return metadata unless the file name is configured to fail."""
        if path.name in self._failing_names:
            raise ValueError("invalid image")
        return PhotoMetadata(width=640, height=480, file_size_bytes=123)


def test_import_people_service_imports_txt_rows(tmp_path: Path) -> None:
    """Import people from a text file into an in-memory repository."""
    source = tmp_path / "people.txt"
    source.write_text(
        "name,identity,department,note\n"
        "Alice,A001,Archive,Team lead\n"
        "Bob,B002,Archive,\n"
        "Alice Duplicate,A001,Other,Skipped\n",
        encoding="utf-8",
    )
    repository = InMemoryPersonRepository()
    service = ImportPeopleService(TxtPersonImportReader(), repository)

    result = service.execute(ImportPeopleCommand(source_path=source))

    assert result.succeeded
    assert result.imported_count == 2
    assert result.skipped_count == 1
    assert [person.name for person in repository.list_all()] == ["Alice", "Bob"]


def test_import_people_service_passes_sheet_name_to_reader(tmp_path: Path) -> None:
    """Forward optional sheet selection from command to reader ports."""
    reader = RecordingPersonImportReader()
    repository = InMemoryPersonRepository()
    service = ImportPeopleService(reader, repository)
    source_path = tmp_path / "people.xlsx"

    result = service.execute(
        ImportPeopleCommand(
            source_path=source_path,
            has_header=False,
            sheet_name="Students",
        )
    )

    assert result.succeeded
    assert reader.source_path == source_path
    assert reader.has_header is False
    assert reader.sheet_name == "Students"


def test_scan_photo_folder_service_discovers_supported_images(tmp_path: Path) -> None:
    """Scan a folder and return only supported image files."""
    image_path = tmp_path / "photo.JPG"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_image_path = nested_dir / "nested.png"
    ignored_path = tmp_path / "notes.txt"

    image_path.write_bytes(b"")
    nested_image_path.write_bytes(b"")
    ignored_path.write_text("not an image", encoding="utf-8")

    service = ScanPhotoFolderService(LocalPhotoFileScanner())
    result = service.execute(ScanPhotoFolderCommand(folder_path=tmp_path, recursive=True))

    assert result.succeeded
    assert result.discovered_count == 2
    assert {item.path for item in result.photos} == {image_path, nested_image_path}


def test_scan_photo_folder_service_returns_filesystem_errors(tmp_path: Path) -> None:
    """Convert expected filesystem errors into result DTO errors."""
    service = ScanPhotoFolderService(FailingPhotoFileScanner(OSError("permission denied")))

    result = service.execute(ScanPhotoFolderCommand(folder_path=tmp_path))

    assert result.succeeded is False
    assert result.errors == ("permission denied",)


def test_scan_photo_folder_service_reraises_unexpected_errors(tmp_path: Path) -> None:
    """Do not hide scanner implementation bugs as normal scan failures."""
    service = ScanPhotoFolderService(FailingPhotoFileScanner(RuntimeError("scanner bug")))

    with pytest.raises(RuntimeError, match="scanner bug"):
        service.execute(ScanPhotoFolderCommand(folder_path=tmp_path))


def test_scan_and_register_photos_service_does_not_create_folder_when_scan_fails(tmp_path: Path) -> None:
    """Avoid persisting folder state when the filesystem scan fails."""
    folder_repository = InMemoryFolderRepository()
    service = ScanAndRegisterPhotosService(
        FailingPhotoFileScanner(OSError("permission denied")),
        folder_repository,
        InMemoryPhotoRepository(),
    )

    result = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert result.succeeded is False
    assert result.folder_id is None
    assert result.failed_count == 1
    assert result.errors == ("permission denied",)
    assert folder_repository.list_all() == []


def test_register_photo_service_registers_photo_with_metadata(tmp_path: Path) -> None:
    """Register a photo and avoid creating a duplicate for the same path."""
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"")
    repository = InMemoryPhotoRepository()
    service = RegisterPhotoService(repository)

    first_result = service.execute(RegisterPhotoCommand(path=image_path))
    second_result = service.execute(RegisterPhotoCommand(path=image_path))

    assert first_result.created is True
    assert second_result.created is False
    assert second_result.photo_id == first_result.photo_id
    assert len(repository.list_all()) == 1
    photo = repository.find_by_id(first_result.photo_id)
    assert photo is not None
    assert photo.metadata is None


def test_register_photo_service_normalizes_relative_path_separators() -> None:
    """Treat equivalent relative path separator forms as the same photo path."""
    repository = InMemoryPhotoRepository()
    service = RegisterPhotoService(repository)

    first_result = service.execute(RegisterPhotoCommand(path=Path("school/event.jpg")))
    second_result = service.execute(RegisterPhotoCommand(path=Path("school\\event.jpg")))

    assert first_result.created is True
    assert second_result.created is False
    assert second_result.photo_id == first_result.photo_id


def test_scan_and_register_photos_service_registers_folder_photos_and_counters(tmp_path: Path) -> None:
    """Scan a folder, register discovered photos, and update folder counters."""
    image_path = tmp_path / "photo.jpg"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_image_path = nested_dir / "nested.png"
    ignored_path = tmp_path / "notes.txt"
    image_path.write_bytes(b"image")
    nested_image_path.write_bytes(b"image")
    ignored_path.write_text("not an image", encoding="utf-8")
    folder_repository = InMemoryFolderRepository()
    photo_repository = InMemoryPhotoRepository()
    service = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(),
        folder_repository,
        photo_repository,
        SelectiveFailingMetadataReader(),
    )

    first_result = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))
    second_result = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert first_result.succeeded
    assert first_result.discovered_count == 2
    assert first_result.registered_count == 2
    assert first_result.skipped_count == 0
    assert second_result.registered_count == 0
    assert second_result.skipped_count == 2
    assert len(photo_repository.list_all()) == 2
    folder = folder_repository.find_by_id(first_result.folder_id)
    assert folder is not None
    assert folder.total_photos == 2
    assert folder.scanned_photos == 2
    assert {photo.folder_id for photo in photo_repository.list_all()} == {folder.id}
    assert all(photo.metadata is not None for photo in photo_repository.list_all())


def test_scan_and_register_photos_service_records_item_failures(tmp_path: Path) -> None:
    """Continue registering later photos when one metadata read fails."""
    bad_image_path = tmp_path / "bad.jpg"
    good_image_path = tmp_path / "good.jpg"
    bad_image_path.write_bytes(b"bad")
    good_image_path.write_bytes(b"good")
    folder_repository = InMemoryFolderRepository()
    photo_repository = InMemoryPhotoRepository()
    service = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(),
        folder_repository,
        photo_repository,
        SelectiveFailingMetadataReader({"bad.jpg"}),
    )

    result = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert result.succeeded is False
    assert result.discovered_count == 2
    assert result.registered_count == 1
    assert result.failed_count == 1
    assert "bad.jpg" in result.errors[0]
    assert len(photo_repository.list_all()) == 1
    folder = folder_repository.find_by_id(result.folder_id)
    assert folder is not None
    assert folder.total_photos == 2
    assert folder.scanned_photos == 1