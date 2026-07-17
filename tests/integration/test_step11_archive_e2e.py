"""End-to-end integration test for Phase 2 Step 11 archive workflow.

Runs the real SQLite connection provider + real Pillow metadata reader + real
ArchivePathBuilderService + ArchivePlanner + ArchiveExecutor + ArchivePhotosService
+ SQLiteUnitOfWork, over a tmp_path photo source and archive root.

Unlike test_step10_e2e.py this test does NOT depend on the InsightFace model pack
— archive consumes already-approved RecognitionResult aggregates, no detection runs.
Schema upgrade to PRAGMA user_version=4 (photos.captured_at + archive_records table)
is implicitly verified by the SQLite connection provider initializing successfully.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from photo_archiver.application.commands import ArchivePhotosCommand
from photo_archiver.application.services import (
    ArchiveExecutor,
    ArchivePathBuilderService,
    ArchivePhotosService,
    ArchivePlanner,
)
from photo_archiver.domain import (
    ArchiveStatus,
    Folder,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)
from photo_archiver.infrastructure import (
    PillowPhotoMetadataReader,
    SQLiteArchiveRecordRepository,
    SQLiteConnectionProvider,
    SQLiteFolderRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
    SQLiteUnitOfWork,
)


@pytest.fixture()
def sqlite_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Initialize a fresh SQLite database with the Step 11 schema (PRAGMA v4)."""
    provider = SQLiteConnectionProvider(tmp_path / "archive_e2e.sqlite3")
    provider.initialize_schema()
    return provider


@pytest.fixture()
def repositories(sqlite_provider: SQLiteConnectionProvider) -> tuple:
    """Build the five repositories needed by the archive workflow."""
    return (
        SQLiteFolderRepository(sqlite_provider),
        SQLitePersonRepository(sqlite_provider),
        SQLitePhotoRepository(sqlite_provider),
        SQLiteRecognitionRepository(sqlite_provider),
        SQLiteArchiveRecordRepository(sqlite_provider),
    )


def _write_photo_on_disk(tmp_path: Path, name: str, content: bytes = b"fake-jpg") -> Path:
    """Materialize a fake JPG on disk so the executor's shutil.copyfile succeeds."""
    source = tmp_path / "photos" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return source


def _seed_approved_workflow(
    tmp_path: Path,
    folders_repo, persons_repo, photos_repo, recognition_repo,
    person_name: str = "Alice",
    captured_at: datetime | None = None,
    photo_name: str = "alice.jpg",
) -> tuple[UUID, UUID]:
    """Seed a person + a photo + an APPROVED recognition, return (person_id, photo_id).

    The photo is materialized on disk under tmp_path/photos so the executor can
    copy it. The photo path is ABSOLUTE so the planner accepts it.
    """
    person = Person(name=person_name)
    persons_repo.add(person)

    source = _write_photo_on_disk(tmp_path, photo_name)
    folder = Folder(path=PhotoPath(source.parent, base=PhotoPathBase.ABSOLUTE), total_photos=1)
    folders_repo.add(folder)

    photo = Photo(
        path=PhotoPath(source, base=PhotoPathBase.ABSOLUTE),
        folder_id=folder.id,
        original_name=photo_name,
        captured_at=captured_at,
    )
    photos_repo.add(photo)

    recognition = RecognitionResult(
        photo_id=photo.id,  # type: ignore[arg-type]
        person_id=person.id,
        confidence=0.92,
    )
    recognition.approve()
    recognition_repo.add(recognition)
    return person.id, photo.id  # type: ignore[return-value]


def test_step11_e2e_archives_approved_photo_under_naming_rule(
    tmp_path: Path,
    repositories: tuple,
    sqlite_provider: SQLiteConnectionProvider,
) -> None:
    """Full闭环: approved photo → plan → execute → file lands under ARCHIVE_ROOT/{person}/{date}/{file}.

    Verifies裁决 #2 naming rule (YYYY-MM-DD from captured_at) and裁决 #3
    plan/execute split via the real ArchivePhotosService composition.
    """
    folders_repo, persons_repo, photos_repo, recognition_repo, archive_repo = repositories
    person_id, photo_id = _seed_approved_workflow(
        tmp_path, folders_repo, persons_repo, photos_repo, recognition_repo,
        captured_at=datetime(2024, 5, 1, 9, 30, 0),
    )

    archive_root = tmp_path / "archive"
    planner = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=persons_repo,
        photo_repository=photos_repo,
        recognition_repository=recognition_repo,
        archive_record_repository=archive_repo,
    )
    executor = ArchiveExecutor(archive_repo)
    service = ArchivePhotosService(
        planner=planner,
        executor=executor,
        unit_of_work=SQLiteUnitOfWork(sqlite_provider),
    )

    result = service.execute(ArchivePhotosCommand(
        archive_root=archive_root,
        person_ids=(person_id,),
        conflict_strategy="skip",
    ))

    assert result.planned_count == 1
    assert result.archived_count == 1
    assert result.failed_count == 0
    target = archive_root / "Alice" / "2024-05-01" / "alice.jpg"
    assert target.exists()
    assert target.read_bytes() == b"fake-jpg"

    record = archive_repo.find_by_photo(photo_id)
    assert record is not None
    assert record.status is ArchiveStatus.ARCHIVED
    assert record.target_person_name == "Alice"
    assert record.target_event_or_date == "2024-05-01"
    assert record.target_original_name == "alice.jpg"


def test_step11_e2e_dry_run_does_not_write_filesystem(
    tmp_path: Path,
    repositories: tuple,
    sqlite_provider: SQLiteConnectionProvider,
) -> None:
    """dry_run=True → DRY_RUN status, archive_root stays empty, record persists."""
    folders_repo, persons_repo, photos_repo, recognition_repo, archive_repo = repositories
    person_id, _ = _seed_approved_workflow(
        tmp_path, folders_repo, persons_repo, photos_repo, recognition_repo,
        captured_at=datetime(2024, 5, 1),
    )

    archive_root = tmp_path / "archive"
    planner = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=persons_repo,
        photo_repository=photos_repo,
        recognition_repository=recognition_repo,
        archive_record_repository=archive_repo,
    )
    executor = ArchiveExecutor(archive_repo)
    service = ArchivePhotosService(
        planner=planner, executor=executor, unit_of_work=SQLiteUnitOfWork(sqlite_provider),
    )

    result = service.execute(ArchivePhotosCommand(
        archive_root=archive_root, person_ids=(person_id,), dry_run=True,
    ))
    assert result.dry_run_count == 1
    assert not archive_root.exists() or not any(archive_root.rglob("*.jpg"))


def test_step11_e2e_skip_strategy_skips_second_run(
    tmp_path: Path,
    repositories: tuple,
    sqlite_provider: SQLiteConnectionProvider,
) -> None:
    """Re-running archive after the photo is already archived skips it (no double-write)."""
    folders_repo, persons_repo, photos_repo, recognition_repo, archive_repo = repositories
    person_id, _ = _seed_approved_workflow(
        tmp_path, folders_repo, persons_repo, photos_repo, recognition_repo,
        captured_at=datetime(2024, 5, 1),
    )

    archive_root = tmp_path / "archive"
    planner = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=persons_repo,
        photo_repository=photos_repo,
        recognition_repository=recognition_repo,
        archive_record_repository=archive_repo,
    )
    executor = ArchiveExecutor(archive_repo)
    service = ArchivePhotosService(
        planner=planner, executor=executor, unit_of_work=SQLiteUnitOfWork(sqlite_provider),
    )

    first = service.execute(ArchivePhotosCommand(archive_root=archive_root, person_ids=(person_id,)))
    second = service.execute(ArchivePhotosCommand(archive_root=archive_root, person_ids=(person_id,)))
    assert first.archived_count == 1
    # Second run finds the existing ArchiveRecord (status ARCHIVED, past PLANNED)
    # → planner skips → executor never sees the item.
    assert second.planned_count == 0


def test_step11_e2e_unknown_date_segment_when_captured_at_missing(
    tmp_path: Path,
    repositories: tuple,
    sqlite_provider: SQLiteConnectionProvider,
) -> None:
    """Photo without captured_at archives under the unknown-date placeholder segment."""
    folders_repo, persons_repo, photos_repo, recognition_repo, archive_repo = repositories
    person_id, _ = _seed_approved_workflow(
        tmp_path, folders_repo, persons_repo, photos_repo, recognition_repo,
        captured_at=None,  # no EXIF / no captured_at
    )

    archive_root = tmp_path / "archive"
    planner = ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=persons_repo,
        photo_repository=photos_repo,
        recognition_repository=recognition_repo,
        archive_record_repository=archive_repo,
    )
    executor = ArchiveExecutor(archive_repo)
    service = ArchivePhotosService(
        planner=planner, executor=executor, unit_of_work=SQLiteUnitOfWork(sqlite_provider),
    )

    result = service.execute(ArchivePhotosCommand(archive_root=archive_root, person_ids=(person_id,)))
    assert result.archived_count == 1
    target = archive_root / "Alice" / "unknown-date" / "alice.jpg"
    assert target.exists()


def test_step11_e2e_pillow_metadata_reader_fills_captured_at(
    tmp_path: Path,
    sqlite_provider: SQLiteConnectionProvider,
) -> None:
    """PillowPhotoMetadataReader reads real file mtime into captured_at (EXIF fallback).

    This verifies the裁决 #2 ingest-stage contract: the reader is the only source
    of captured_at, and absent EXIF it falls back to file mtime. We materialize
    a tiny real JPEG via PIL so Pillow can Image.open() it (a bare b"fake-jpg"
    blob is not a valid JPEG and would trip UnidentifiedImageError). We do not
    assert an exact timestamp (mtime varies by filesystem), only that captured_at
    is populated when the reader runs over a real file.
    """
    pytest.importorskip("PIL")
    from PIL import Image

    source = tmp_path / "photos" / "minimal.jpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    # 1×1 RGB JPEG — Pillow accepts it, no EXIF present → mtime fallback engages.
    Image.new("RGB", (1, 1)).save(source, format="JPEG")

    reader = PillowPhotoMetadataReader()
    metadata = reader.read(source)
    assert metadata.captured_at is not None
    # mtime fallback should land within a few seconds of now (file was just written).
    delta = abs((datetime.now() - metadata.captured_at).total_seconds())
    assert delta < 60
