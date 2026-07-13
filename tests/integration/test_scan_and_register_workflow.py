"""Integration tests for scanning real image files into SQLite."""

from pathlib import Path

import pytest

from photo_archiver.app import bootstrap_application
from photo_archiver.application import ScanAndRegisterPhotosCommand
from photo_archiver.domain import PhotoPath, PhotoPathBase
from photo_archiver.infrastructure.config import AppSettings

Image = pytest.importorskip("PIL.Image")


def test_bootstrapped_scan_and_register_persists_real_photo(tmp_path: Path) -> None:
    """A bootstrapped app can scan, read metadata, and persist a real photo."""
    photo_folder = tmp_path / "photos"
    photo_folder.mkdir()
    photo_path = photo_folder / "family.jpg"
    Image.new("RGB", (8, 6), color="white").save(photo_path)

    context = bootstrap_application(
        AppSettings(
            database_url=f"sqlite:///{tmp_path / 'photo_archiver.sqlite3'}",
            log_directory=tmp_path / "logs",
            model_path=tmp_path / "models",
        )
    )

    result = context.services.scan_and_register_photos.execute(
        ScanAndRegisterPhotosCommand(folder_path=photo_folder, folder_display_name="Family")
    )

    assert result.succeeded is True
    assert result.discovered_count == 1
    assert result.registered_count == 1
    assert result.skipped_count == 0
    assert result.failed_count == 0

    folder = context.repositories.folders.find_by_id(result.folder_id)
    assert folder is not None
    assert folder.display_name == "Family"
    assert folder.total_photos == 1
    assert folder.scanned_photos == 1

    photos = context.repositories.photos.list_by_folder_id(folder.id)
    assert len(photos) == 1
    assert photos[0].path == PhotoPath(photo_path.resolve(), PhotoPathBase.ABSOLUTE)
    assert photos[0].original_name == "family.jpg"
    assert photos[0].metadata is not None
    assert photos[0].metadata.width == 8
    assert photos[0].metadata.height == 6

    second_result = context.services.scan_and_register_photos.execute(
        ScanAndRegisterPhotosCommand(folder_path=photo_folder)
    )

    assert second_result.registered_count == 0
    assert second_result.skipped_count == 1
    assert context.repositories.photos.list_by_folder_id(folder.id) == photos