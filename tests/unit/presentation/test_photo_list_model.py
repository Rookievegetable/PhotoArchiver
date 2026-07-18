"""Tests for PhotoListModel — QAIM contract + thumbnail role flow."""

import pytest

pytest.importorskip("PySide6")

from pathlib import Path
from uuid import uuid4

from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase
from photo_archiver.presentation.views.photo_list_model import (
    ORIGINAL_NAME_ROLE,
    PHOTO_ID_ROLE,
    THUMBNAIL_ROLE,
    PhotoListModel,
)


def _make_photo(name: str = "x.jpg") -> Photo:
    return Photo(
        path=PhotoPath(Path.cwd() / name, base=PhotoPathBase.ABSOLUTE),
        original_name=name,
    )


def test_load_photos_replaces_model_rows() -> None:
    """load_photos() resets the model and rowCount tracks the new list."""
    model = PhotoListModel()
    assert model.rowCount() == 0
    model.load_photos([_make_photo("a.jpg"), _make_photo("b.jpg")])
    assert model.rowCount() == 2


def test_data_returns_original_name_for_display_role() -> None:
    """Qt.DisplayRole returns the photo's original_name as the row label."""
    from PySide6.QtCore import Qt

    model = PhotoListModel()
    photo = _make_photo("alice.jpg")
    model.load_photos([photo])
    idx = model.index(0, 0)
    assert model.data(idx, Qt.DisplayRole) == "alice.jpg"


def test_data_returns_fields_for_custom_roles() -> None:
    """Custom roles surface original_name, thumbnail, and photo_id for delegates."""
    model = PhotoListModel()
    photo = _make_photo("alice.jpg")
    model.load_photos([photo])
    idx = model.index(0, 0)
    assert model.data(idx, ORIGINAL_NAME_ROLE) == "alice.jpg"
    assert model.data(idx, PHOTO_ID_ROLE) == photo.id
    # Thumbnail not loaded yet -> None
    assert model.data(idx, THUMBNAIL_ROLE) is None


def test_set_thumbnail_populates_thumbnail_role() -> None:
    """set_thumbnail() caches the path so THUMBNAIL_ROLE returns it."""
    model = PhotoListModel()
    photo = _make_photo("alice.jpg")
    model.load_photos([photo])
    thumb = Path("/cache/thumb.jpg")
    model.set_thumbnail(photo.id, thumb)
    idx = model.index(0, 0)
    assert model.data(idx, THUMBNAIL_ROLE) == thumb


def test_set_thumbnail_for_unknown_photo_id_is_noop() -> None:
    """set_thumbnail() for a photo not in the model is a silent no-op (no crash)."""
    model = PhotoListModel()
    model.load_photos([_make_photo("a.jpg")])
    # Should not raise
    model.set_thumbnail(uuid4(), Path("/cache/x.jpg"))


def test_data_for_invalid_row_returns_none() -> None:
    """data() for an out-of-range row returns None per QAIM convention."""
    from PySide6.QtCore import Qt

    model = PhotoListModel()
    model.load_photos([_make_photo("a.jpg")])
    idx = model.index(99, 0)
    assert model.data(idx, Qt.DisplayRole) is None
