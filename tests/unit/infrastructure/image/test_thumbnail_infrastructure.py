"""Tests for thumbnail generator and cache infrastructure."""

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from photo_archiver.infrastructure.image import (
    ContentHashCalculator,
    PillowThumbnailGenerator,
    ThumbnailCache,
)


def test_thumbnail_cache_resolve_is_deterministic(tmp_path: Path) -> None:
    """Same source+size should resolve to the same cache path."""
    cache = ThumbnailCache(tmp_path / "thumbs")
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"x")
    a = cache.resolve(source, 256)
    b = cache.resolve(source, 256)
    assert a == b
    assert tmp_path / "thumbs" in a.parents


def test_thumbnail_cache_is_stale_when_missing(tmp_path: Path) -> None:
    """Cache should report stale when the thumbnail file does not exist."""
    cache = ThumbnailCache(tmp_path / "thumbs")
    cached = tmp_path / "thumbs" / "missing.jpg"
    assert cache.is_stale(tmp_path / "src.jpg", cached) is True


def test_pillow_thumbnail_generator_creates_cache_on_miss(tmp_path: Path) -> None:
    """Generator should render and write the thumbnail on a cache miss."""
    from PIL import Image

    source = tmp_path / "photo.jpg"
    Image.new("RGB", (1024, 768), color="white").save(source)
    cache = ThumbnailCache(tmp_path / "thumbs")
    generator = PillowThumbnailGenerator(cache)

    result = generator.generate(source, 256)

    assert result.exists()
    with Image.open(result) as thumb:
        assert max(thumb.size) <= 256


def test_pillow_thumbnail_generator_hits_cache_on_second_call(tmp_path: Path) -> None:
    """Second call with same source+size should return same path without re-render."""
    from PIL import Image

    source = tmp_path / "photo.jpg"
    Image.new("RGB", (512, 512), color="black").save(source)
    cache = ThumbnailCache(tmp_path / "thumbs")
    generator = PillowThumbnailGenerator(cache)

    first = generator.generate(source, 128)
    first_mtime = first.stat().st_mtime_ns

    second = generator.generate(source, 128)
    assert second == first
    assert second.stat().st_mtime_ns == first_mtime


def test_content_hash_calculator_is_stable(tmp_path: Path) -> None:
    """Same bytes should produce the same SHA-256 hex digest."""
    source = tmp_path / "a.bin"
    source.write_bytes(b"identical content")
    calc = ContentHashCalculator()
    assert calc.calculate(source) == calc.calculate(source)


def test_content_hash_calculator_distinguishes_content(tmp_path: Path) -> None:
    """Different bytes should produce different hashes."""
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"content a")
    b.write_bytes(b"content b")
    calc = ContentHashCalculator()
    assert calc.calculate(a) != calc.calculate(b)
