"""Tests for application bootstrap dependency assembly."""

from pathlib import Path

import pytest

import photo_archiver.app.bootstrap as bootstrap_module
from photo_archiver.app import ApplicationRepositories, ApplicationServices, bootstrap_application
from photo_archiver.domain import Folder, Person, PersonIdentity, Photo, PhotoPath
from photo_archiver.infrastructure.config import AppSettings


def build_settings(tmp_path: Path) -> AppSettings:
    """Build isolated settings for bootstrap tests."""
    return AppSettings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'data' / 'app.db'}",
        log_directory=tmp_path / "logs",
        model_path=tmp_path / "models",
    )


def test_bootstrap_application_assembles_sqlite_repositories(tmp_path: Path) -> None:
    """Bootstrap initializes runtime directories, SQLite schema, and repositories."""
    settings = build_settings(tmp_path)

    context = bootstrap_application(settings)

    assert context.settings is settings
    assert isinstance(context.repositories, ApplicationRepositories)
    assert isinstance(context.services, ApplicationServices)
    assert context.repositories.folders is not None
    assert context.repositories.photos is not None
    assert context.services.scan_and_register_photos is not None
    assert settings.database_path.exists()

    person = Person(name="Alice", identity=PersonIdentity("A001"))
    context.repositories.people.add(person)
    folder = Folder(path=PhotoPath("school"), total_photos=1)
    context.repositories.folders.add(folder)
    photo = Photo(path=PhotoPath("school/event.jpg"), folder_id=folder.id)
    context.repositories.photos.add(photo)

    assert context.repositories.people.find_by_identity(PersonIdentity("A001")) == person
    assert context.repositories.folders.find_by_path(PhotoPath("school")) == folder
    assert context.repositories.photos.find_by_path(PhotoPath("school/event.jpg")) == photo


def test_bootstrap_application_reraises_repository_initialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap preserves repository initialization failures for callers."""
    settings = build_settings(tmp_path)
    expected_error = RuntimeError("database unavailable")

    def fail_build_sqlite_repositories(database_path: Path) -> ApplicationRepositories:
        raise expected_error

    monkeypatch.setattr(
        bootstrap_module,
        "build_sqlite_repositories",
        fail_build_sqlite_repositories,
    )

    with pytest.raises(RuntimeError) as exc_info:
        bootstrap_application(settings)

    assert exc_info.value is expected_error
