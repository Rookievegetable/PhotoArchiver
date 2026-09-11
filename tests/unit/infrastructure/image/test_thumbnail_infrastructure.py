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


def test_thumbnail_cache_compute_key_matches_resolve_name(tmp_path: Path) -> None:
    """compute_key embeds the same digest resolve() uses for the file name."""
    cache = ThumbnailCache(tmp_path / "thumbs")
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"x")
    resolved = cache.resolve(source, 256)
    assert resolved is not None
    assert cache.compute_key(source, 256) == resolved.stem


def test_thumbnail_cache_compute_key_none_for_missing_source(tmp_path: Path) -> None:
    cache = ThumbnailCache(tmp_path / "thumbs")
    assert cache.compute_key(tmp_path / "gone.jpg", 256) is None


def test_thumbnail_cache_cleanup_removes_only_orphans_on_execute(
    tmp_path: Path,
) -> None:
    """ISSUE-023: dry-run counts without deleting; --execute removes orphans only."""
    cache = ThumbnailCache(tmp_path / "thumbs")
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"x")
    live_key = cache.compute_key(source, 256)
    assert live_key is not None
    live_file = tmp_path / "thumbs" / f"{live_key}.jpg"
    live_file.write_bytes(b"thumb")
    orphan = tmp_path / "thumbs" / ("f" * 24 + ".jpg")  # 24 hex + ext = 孤儿形态
    orphan.write_bytes(b"stale")
    foreign = tmp_path / "thumbs" / "not-a-cache-entry.txt"  # 外来文件不可触碰
    foreign.write_bytes(b"user-data")
    removed, retained = cache.cleanup({live_key}, dry_run=True)
    assert (removed, retained) == (1, 2)
    assert orphan.exists() and live_file.exists()  # dry-run 不删

    removed, retained = cache.cleanup({live_key}, dry_run=False)
    assert (removed, retained) == (1, 2)
    assert not orphan.exists()
    assert live_file.exists()
    assert foreign.exists()  # 外来文件永不清理
