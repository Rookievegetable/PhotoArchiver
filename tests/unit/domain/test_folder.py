"""Tests for folder domain entity."""

import pytest

from photo_archiver.domain import Folder, PhotoPath, ValidationError


def test_folder_accepts_valid_scan_counts() -> None:
    """Folder stores valid scan progress counters."""
    folder = Folder(
        path=PhotoPath("photos"),
        display_name="  School Archive  ",
        total_photos=10,
        scanned_photos=3,
    )

    assert folder.id is not None
    assert folder.display_name == "School Archive"
    assert folder.total_photos == 10
    assert folder.scanned_photos == 3


def test_folder_rejects_scanned_count_above_total() -> None:
    """Folder scan progress cannot exceed its total photo count."""
    with pytest.raises(ValidationError):
        Folder(path=PhotoPath("photos"), total_photos=1, scanned_photos=2)


def test_folder_requires_photo_path_value_object() -> None:
    """Folder path must use the domain value object."""
    with pytest.raises(ValidationError):
        Folder(path=None)  # type: ignore[arg-type]