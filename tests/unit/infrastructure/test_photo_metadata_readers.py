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

def _write_jpeg_with_exif(tmp_path: Path, name: str, sub_ifd: dict, ifd0: dict | None = None) -> Path:
    """Write a JPEG carrying EXIF in the standard sub-IFD and/or IFD0 top level."""
    from PIL import Image

    source = tmp_path / name
    image = Image.new("RGB", (64, 48), color="white")
    exif = Image.Exif()
    for tag, value in (ifd0 or {}).items():
        exif[tag] = value
    for tag, value in sub_ifd.items():
        exif.get_ifd(0x8769)[tag] = value
    image.save(source, "JPEG", exif=exif)
    return source


def test_standard_exif_sub_ifd_datetime_original_hits(tmp_path: Path) -> None:
    """ISSUE-019 回归：标准 Exif 子 IFD DateTimeOriginal 必须命中（此前落 mtime）。"""
    from datetime import datetime

    source = _write_jpeg_with_exif(
        tmp_path, "sub_original.jpg", {36867: "2026:03:15 10:30:00"}
    )

    metadata = PillowPhotoMetadataReader().read(source)

    assert metadata.captured_at == datetime(2026, 3, 15, 10, 30, 0)
    assert metadata.captured_at != metadata.modified_at


def test_standard_exif_sub_ifd_datetime_digitized_fallback_hits(tmp_path: Path) -> None:
    """子 IFD 只有 DateTimeDigitized 时按链降级命中。"""
    from datetime import datetime

    source = _write_jpeg_with_exif(
        tmp_path, "sub_digitized.jpg", {36868: "2025:12:01 08:00:00"}
    )

    metadata = PillowPhotoMetadataReader().read(source)

    assert metadata.captured_at == datetime(2025, 12, 1, 8, 0, 0)


def test_sub_ifd_datetime_original_takes_priority_over_digitized(tmp_path: Path) -> None:
    """子 IFD 同持 36867/36868 时 Original 优先；IFD0 顶层兜底劣后于子 IFD。"""
    from datetime import datetime

    both = _write_jpeg_with_exif(
        tmp_path,
        "both.jpg",
        {36867: "2026:03:15 10:30:00", 36868: "2025:12:01 08:00:00"},
        ifd0={36868: "2020:01:01 00:00:00"},
    )
    assert PillowPhotoMetadataReader().read(both).captured_at == datetime(
        2026, 3, 15, 10, 30, 0
    )

    only_ifd0 = _write_jpeg_with_exif(
        tmp_path, "ifd0.jpg", {}, ifd0={36868: "2020:01:01 00:00:00"}
    )
    assert PillowPhotoMetadataReader().read(only_ifd0).captured_at == datetime(
        2020, 1, 1, 0, 0, 0
    )


def test_unparsable_sub_ifd_datetime_falls_through_to_mtime(tmp_path: Path) -> None:
    """子 IFD 值不可解析时不抛错、继续降级链，最终落 mtime 兜底。"""
    source = _write_jpeg_with_exif(
        tmp_path, "unparsable.jpg", {36867: "not-a-datetime"}
    )

    metadata = PillowPhotoMetadataReader().read(source)

    assert metadata.captured_at == metadata.modified_at
