"""Tests for photo metadata reader infrastructure adapters."""

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from photo_archiver.infrastructure import PillowPhotoMetadataReader


def test_pillow_photo_metadata_reader_reads_image_metadata(tmp_path: Path) -> None:
    """Read dimensions and filesystem metadata from a valid image file."""
    from PIL import Image

    source = tmp_path / "photo.jpg"
    Image.new("RGB", (320, 240), color="white").save(source)

    metadata = PillowPhotoMetadataReader().read(source)

    assert metadata.width == 320
    assert metadata.height == 240
    assert metadata.file_size_bytes == source.stat().st_size
    assert metadata.modified_at is not None


def test_pillow_photo_metadata_reader_raises_for_missing_file(tmp_path: Path) -> None:
    """Surface missing photo paths as FileNotFoundError."""
    source = tmp_path / "missing.jpg"

    with pytest.raises(FileNotFoundError, match="Photo file does not exist"):
        PillowPhotoMetadataReader().read(source)


def test_pillow_photo_metadata_reader_raises_for_directory_path(tmp_path: Path) -> None:
    """Reject directory paths before invoking Pillow."""
    with pytest.raises(IsADirectoryError, match="Photo path is not a file"):
        PillowPhotoMetadataReader().read(tmp_path)


def test_pillow_photo_metadata_reader_raises_for_invalid_image(tmp_path: Path) -> None:
    """Convert unsupported or corrupted image files into ValueError."""
    source = tmp_path / "broken.jpg"
    source.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported or invalid image file"):
        PillowPhotoMetadataReader().read(source)