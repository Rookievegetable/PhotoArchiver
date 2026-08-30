"""Decompression-bomb guard negative tests (P2-002 fix).

Verifies, with real Pillow decoding (no mocks on the image path):
- a hostile oversized image header is refused by both adapters with a clear
  error mapped onto the existing per-photo error types;
- normal images keep passing while the guard is active;
- corrupted images keep their historical error mapping;
- one refused photo does not abort a scan batch (real scanner + in-memory
  repositories, integration-style but dependency-light).
"""

import struct
import zlib
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from PIL import Image

from photo_archiver.application import (
    ScanAndRegisterPhotosCommand,
    ScanAndRegisterPhotosService,
)
from photo_archiver.infrastructure import (
    InMemoryFolderRepository,
    InMemoryPhotoRepository,
    LocalPhotoFileScanner,
)
from photo_archiver.infrastructure.filesystem import PillowPhotoMetadataReader
from photo_archiver.infrastructure.image import (
    ContentHashCalculator,
    PillowThumbnailGenerator,
    ThumbnailCache,
)

# Small non-default guard so tests exercise the configured-limit path.
GUARD = 1_000_000
BOMB_SIDE = 100_000  # 1e10 pixels >> 2 * GUARD


@pytest.fixture(autouse=True)
def _restore_global_pixel_guard():
    """Save/restore Pillow's process-global pixel limit around each test."""
    saved = Image.MAX_IMAGE_PIXELS
    yield
    Image.MAX_IMAGE_PIXELS = saved


def _write_bomb_png(path: Path) -> None:
    """Write a tiny PNG whose IHDR declares a huge pixel canvas."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        piece = struct.pack(">I", len(data)) + tag + data
        return piece + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", BOMB_SIDE, BOMB_SIDE, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 8))
        + chunk(b"IEND", b"")
    )


def test_metadata_reader_refuses_bomb_image(tmp_path: Path) -> None:
    bomb = tmp_path / "bomb.png"
    _write_bomb_png(bomb)
    reader = PillowPhotoMetadataReader(max_image_pixels=GUARD)

    with pytest.raises(ValueError, match="MAX_IMAGE_PIXELS"):
        reader.read(bomb)


def test_thumbnail_generator_refuses_bomb_image(tmp_path: Path) -> None:
    bomb = tmp_path / "bomb.png"
    _write_bomb_png(bomb)
    generator = PillowThumbnailGenerator(
        ThumbnailCache(tmp_path / "thumbs"), max_image_pixels=GUARD
    )

    with pytest.raises(OSError, match="MAX_IMAGE_PIXELS"):
        generator.generate(bomb, 128)


def test_normal_image_still_passes_with_guard(tmp_path: Path) -> None:
    source = tmp_path / "photo.png"
    Image.new("RGB", (64, 48), color="white").save(source)
    reader = PillowPhotoMetadataReader(
        content_hasher=ContentHashCalculator(), max_image_pixels=GUARD
    )

    metadata = reader.read(source)

    assert (metadata.width, metadata.height) == (64, 48)
    assert metadata.content_hash


def test_corrupted_image_keeps_value_error_mapping(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"this is not an image")
    reader = PillowPhotoMetadataReader(max_image_pixels=GUARD)

    with pytest.raises(ValueError, match="Unsupported or invalid"):
        reader.read(broken)


def test_bomb_photo_does_not_abort_batch_scan(tmp_path: Path) -> None:
    """One oversized photo fails per-photo; the rest of the batch registers."""
    _write_bomb_png(tmp_path / "bomb.png")
    good = tmp_path / "good.png"
    Image.new("RGB", (32, 32), color="white").save(good)

    reader = PillowPhotoMetadataReader(max_image_pixels=GUARD)
    service = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(),
        InMemoryFolderRepository(),
        InMemoryPhotoRepository(),
        reader,
    )

    result = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert result.registered_count == 1
    assert result.failed_count == 1
    assert "MAX_IMAGE_PIXELS" in result.errors[0]
