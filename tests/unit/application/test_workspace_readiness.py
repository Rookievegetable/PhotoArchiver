"""Readiness service workflows using SQLite adapters and environment test doubles."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from photo_archiver.app.repositories import ApplicationRepositories, build_sqlite_repositories
from photo_archiver.app.services import archive_root_available, build_application_services
from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.application.services.workspace_readiness import WorkspaceReadinessService
from photo_archiver.application.services import ArchivePathBuilderService, ArchivePlanner
from photo_archiver.domain import (
    ArchiveRecord,
    ArchiveStatus,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionRepository,
    RecognitionResult,
)
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.domain.repositories.recognition_repository import WorkspaceCounts


@pytest.fixture
def repositories(tmp_path: Path) -> ApplicationRepositories:
    return build_sqlite_repositories(tmp_path / "readiness.sqlite3")


def _photo(repositories: ApplicationRepositories, path: Path) -> Photo:
    photo = Photo(path=PhotoPath(
        path, base=PhotoPathBase.ABSOLUTE if path.is_absolute() else PhotoPathBase.PHOTO_ROOT,
    ))
    repositories.photos.add(photo)
    return photo


def _recognition(
    repositories: ApplicationRepositories, photo: Photo,
    status: MatchStatus, person: Person | None = None,
) -> RecognitionResult:
    assert photo.id is not None
    result = RecognitionResult(
        photo_id=photo.id, confidence=0.9, status=status,
        person_id=person.id if person else None,
    )
    repositories.recognition.add(result)
    return result


def test_empty_workspace(repositories: ApplicationRepositories) -> None:
    probe = Mock(return_value=True)
    service = WorkspaceReadinessService(repositories.recognition, archive_root_probe=probe)

    assert service.execute(None) == WorkspaceStatus(
        has_persons=False,
        has_photos=False,
        pending_match_count=0,
        pending_review_count=0,
        archivable_count=0,
        archive_root_available=False,
        model_availability=ModelAvailability.UNKNOWN,
    )
    probe.assert_not_called()


@pytest.mark.parametrize("availability", list(ModelAvailability))
@pytest.mark.parametrize("root_available", [False, True])
def test_snapshot_maps_one_aggregate_read(
    availability: ModelAvailability, root_available: bool, tmp_path: Path,
) -> None:
    repository = Mock(spec=RecognitionRepository)
    repository.read_workspace_counts.return_value = WorkspaceCounts(True, True, 7, 9, 2)
    probe = Mock(return_value=root_available)
    service = WorkspaceReadinessService(
        repository, archive_root_probe=probe, model_availability=availability,
    )
    status = service.execute(tmp_path)
    assert status == WorkspaceStatus(True, True, 7, 9, 2, root_available, availability)
    assert repository.mock_calls == [call.read_workspace_counts()]
    probe.assert_called_once_with(tmp_path)
    with pytest.raises(FrozenInstanceError):
        status.has_photos = False  # type: ignore[misc]


def test_archive_root_check_is_read_only(tmp_path: Path) -> None:
    assert archive_root_available(tmp_path)
    proposed = tmp_path / "new" / "nested"
    assert archive_root_available(proposed)
    assert not proposed.parent.exists()
    blocking_file = tmp_path / "file"
    blocking_file.write_text("not a directory", encoding="utf-8")
    assert not archive_root_available(blocking_file)
    assert not archive_root_available(blocking_file / "nested")


def test_archive_root_requires_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    access = Mock(return_value=False)
    monkeypatch.setattr("photo_archiver.app.services.os.access", access)
    assert not archive_root_available(tmp_path / "new" / "nested")
    access.assert_called_once()
    assert access.call_args.args[0] == tmp_path


def test_probe_errors_are_not_disguised_as_availability(
    repositories: ApplicationRepositories, tmp_path: Path,
) -> None:
    service = WorkspaceReadinessService(
        repositories.recognition, archive_root_probe=Mock(side_effect=RuntimeError("probe bug")),
    )
    with pytest.raises(RuntimeError, match="probe bug"):
        service.execute(tmp_path)


def test_counts_refresh_after_scan_match_review_and_delete(
    repositories: ApplicationRepositories, tmp_path: Path,
) -> None:
    service = WorkspaceReadinessService(repositories.recognition, archive_root_probe=lambda _: True)
    person = Person(name="Alice")
    repositories.people.add(person)
    assert service.execute(None).has_persons
    assert not service.execute(None).has_photos
    photo = _photo(repositories, tmp_path / "never-created.jpg")
    other = _photo(repositories, tmp_path / "other.jpg")
    assert service.execute(None).pending_match_count == 2
    first = _recognition(repositories, photo, MatchStatus.PENDING, person)
    second = _recognition(repositories, photo, MatchStatus.PENDING)
    assert service.execute(None).pending_match_count == 1
    assert service.execute(None).pending_review_count == 2
    repositories.recognition.update_status(first.id, MatchStatus.APPROVED)
    repositories.recognition.update_status(second.id, MatchStatus.REJECTED)
    assert service.execute(None).pending_review_count == 0
    assert service.execute(None).archivable_count == 1
    assert person.id is not None
    repositories.people.remove(person.id)
    assert service.execute(None).archivable_count == 0
    assert not service.execute(None).has_persons
    assert photo.id is not None and other.id is not None
    repositories.photos.remove([photo.id, other.id])
    assert not service.execute(None).has_photos
    assert service.execute(None).pending_match_count == 0


@pytest.mark.parametrize("archive_status", [None, *ArchiveStatus])
def test_archive_counts_match_planner_and_deduplicate_photos(
    repositories: ApplicationRepositories, tmp_path: Path, archive_status: ArchiveStatus | None,
) -> None:
    person = Person(name="Alice")
    other_person = Person(name="Bob")
    repositories.people.add(person)
    repositories.people.add(other_person)
    photo = _photo(repositories, tmp_path / "not-on-disk.jpg")
    _recognition(repositories, photo, MatchStatus.APPROVED, person)
    _recognition(repositories, photo, MatchStatus.APPROVED, person)
    _recognition(repositories, photo, MatchStatus.APPROVED, other_person)
    relative = _photo(repositories, Path("relative.jpg"))
    _recognition(repositories, relative, MatchStatus.APPROVED, person)
    unknown = _photo(repositories, tmp_path / "unknown.jpg")
    _recognition(repositories, unknown, MatchStatus.APPROVED)
    rejected = _photo(repositories, tmp_path / "rejected.jpg")
    _recognition(repositories, rejected, MatchStatus.REJECTED, person)
    if archive_status is not None:
        assert photo.id is not None
        repositories.archive_records.add(ArchiveRecord(
            photo_id=photo.id, target_archive_root=str(tmp_path / "archive"),
            target_person_name="Alice", target_event_or_date="unknown-date",
            target_original_name="not-on-disk.jpg", status=archive_status,
        ))
        # A later failed attempt never cancels earlier successful history.
        repositories.archive_records.add(ArchiveRecord(
            photo_id=photo.id, target_archive_root=str(tmp_path / "archive"),
            target_person_name="Alice", target_event_or_date="unknown-date",
            target_original_name="not-on-disk.jpg", status=ArchiveStatus.FAILED,
        ))
    planner = ArchivePlanner(
        ArchivePathBuilderService(), repositories.people, repositories.photos,
        repositories.recognition, repositories.archive_records,
    )
    # E-SG-6：归档拦截按 (person, photo)——Alice 的成功记录只拦 Alice 的
    # 归属，Bob 的同照片归属仍可归档（无成功记录）。
    alice_blocked = archive_status in {
        ArchiveStatus.ARCHIVED, ArchiveStatus.SKIPPED, ArchiveStatus.RENAMED,
        ArchiveStatus.OVERWRITTEN,
    }
    expected = 1 if alice_blocked else 2
    assert planner.plan(str(tmp_path / "archive"), ()).planned_count == expected
    assert repositories.recognition.read_workspace_counts().archivable_count == expected


def test_each_refresh_uses_one_read_only_aggregate_statement(
    repositories: ApplicationRepositories, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed enough rows to distinguish a fixed round trip from per-photo queries.
    with repositories._connection_provider.transaction():
        for index in range(120):
            _photo(repositories, tmp_path / f"absent-{index}.jpg")
    for repository in (repositories.people, repositories.photos, repositories.recognition):
        for name in ("list_all", "search", "list_pending", "list_by_photo"):
            if hasattr(repository, name):
                monkeypatch.setattr(repository, name, Mock(side_effect=AssertionError("enumeration")))
    statements: list[str] = []
    service = WorkspaceReadinessService(repositories.recognition, archive_root_probe=lambda _: True)
    with repositories._connection_provider.transaction() as connection:
        connection.set_trace_callback(statements.append)
        try:
            for _ in range(3):
                assert service.execute(None).pending_match_count == 120
        finally:
            connection.set_trace_callback(None)
    assert len(statements) == 3
    assert all(statement.lstrip().startswith("SELECT") for statement in statements)
    assert all("SELECT *" not in statement.upper() for statement in statements)


@pytest.mark.parametrize("available", [False, True])
def test_assembly_reports_pipeline_readiness_not_changing_model_files(
    repositories: ApplicationRepositories, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, available: bool,
) -> None:
    from photo_archiver.infrastructure.ai import InsightFaceLoader

    availability = Mock(return_value=available)
    load = Mock(return_value=Mock())
    monkeypatch.setattr(InsightFaceLoader, "is_available", availability)
    monkeypatch.setattr(InsightFaceLoader, "load", load)
    settings = AppSettings(model_path=tmp_path / "models", output_root=tmp_path / "output")
    services = build_application_services(repositories, settings)
    expected = ModelAvailability.AVAILABLE if available else ModelAvailability.MISSING
    assert services.workspace_readiness.execute(None).model_availability == expected
    availability.return_value = not available
    settings.model_path.mkdir()
    (settings.model_path / "new-model.onnx").write_bytes(b"arrived after startup")
    assert services.workspace_readiness.execute(tmp_path).model_availability == expected
    availability.assert_called_once()
    assert load.call_count == int(available)
