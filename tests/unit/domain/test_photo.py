"""Tests for photo domain entity and value objects."""

from pathlib import Path

import pytest

from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
    ValidationError,
)


def test_photo_accepts_relative_photo_root_path() -> None:
    """Photo stores portable paths relative to the configured photo root."""
    path = PhotoPath(Path("school/event.jpg"), base=PhotoPathBase.PHOTO_ROOT)
    photo = Photo(path=path, metadata=PhotoMetadata(width=800, height=600))

    assert photo.id is not None
    assert photo.path.is_relative
    assert photo.path.base is PhotoPathBase.PHOTO_ROOT
    assert photo.metadata == PhotoMetadata(width=800, height=600)


def test_photo_path_requires_absolute_base_for_absolute_path() -> None:
    """Absolute paths must be marked explicitly for later resolution."""
    with pytest.raises(ValidationError):
        PhotoPath(Path.cwd(), base=PhotoPathBase.PHOTO_ROOT)


def test_photo_path_rejects_empty_path() -> None:
    """Photo path cannot be empty."""
    with pytest.raises(ValidationError):
        PhotoPath("")


def test_photo_path_rejects_relative_path_with_absolute_base() -> None:
    """Relative paths cannot use the absolute path base."""
    with pytest.raises(ValidationError):
        PhotoPath("event.jpg", base=PhotoPathBase.ABSOLUTE)


def test_photo_requires_photo_path_value_object() -> None:
    """Photo path must use the domain value object."""
    with pytest.raises(ValidationError):
        Photo(path=None)  # type: ignore[arg-type]


def test_photo_metadata_rejects_non_positive_dimensions() -> None:
    """Photo metadata dimensions must be positive when present."""
    with pytest.raises(ValidationError):
        PhotoMetadata(width=0)