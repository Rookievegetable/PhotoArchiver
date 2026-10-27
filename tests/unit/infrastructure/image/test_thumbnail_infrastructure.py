"""Tests for thumbnail generator and cache infrastructure."""

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from PIL import Image

from photo_archiver.infrastructure.image import (
    ContentHashCalculator,
    PillowThumbnailGenerator,
    ThumbnailCache,
)
from photo_archiver.infrastructure.image.thumbnail_cache import RENDER_VERSION


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


# ---- P1：EXIF 方向转正 + 渲染版本缓存失效 ----------------------------------

# EXIF Orientation 5-8 与 PIL 文档化的转置算子一一对应（转正语义的规范出处）。
_ORIENTATIONS = {
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def _striped_source(
    path: Path,
    width: int = 4,
    height: int = 2,
    orientation: int | None = None,
) -> Path:
    """Small lossless fixture: left half red, right half blue; optional EXIF orientation."""
    source = Image.new("RGB", (width, height))
    for x in range(width):
        for y in range(height):
            source.putpixel((x, y), (255, 0, 0) if x < width // 2 else (0, 0, 255))
    exif = None
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
    if exif is None:
        source.save(path)
    else:
        source.save(path, exif=exif)
    return path


@pytest.mark.parametrize(("orientation", "method"), sorted(_ORIENTATIONS.items()))
def test_generator_uprights_exif_orientations_5_to_8(tmp_path, orientation, method) -> None:
    """Orientation 5-8 fixture 的缩略图必须直立：尺寸转置 + 像素与转正结果一致。

    PNG 存储像素不随方向标记旋转（与 JPEG 同语义），且无损——可做像素级断言。
    """
    source = _striped_source(tmp_path / "photo.png", orientation=orientation)
    cache = ThumbnailCache(tmp_path / "thumbs")
    generator = PillowThumbnailGenerator(cache)

    result = generator.generate(source, 256)

    expected = Image.open(source).transpose(method)
    with Image.open(result) as thumb:
        assert thumb.size == expected.size  # 尺寸断言：宽高已转置（不放大）
        assert thumb.size[0] < thumb.size[1]  # 直立：竖版
        assert list(thumb.convert("RGB").getdata()) == list(
            expected.convert("RGB").getdata()
        )  # 像素断言：转置方向与镜像语义均正确


def test_generator_thumbnail_of_rotated_jpeg_is_portrait(tmp_path: Path) -> None:
    """真实格式（JPEG）+ 需缩放：Orientation 6 的 800×200 源产出 64×256 直立缩略图。"""
    source = tmp_path / "photo.jpg"
    _striped_source(source, width=800, height=200, orientation=6)
    generator = PillowThumbnailGenerator(ThumbnailCache(tmp_path / "thumbs"))

    result = generator.generate(source, 256)

    with Image.open(result) as thumb:
        assert thumb.size == (64, 256)


def test_generator_leaves_plain_images_unchanged(tmp_path: Path) -> None:
    """无方向标记的源：转正路径退化为副本，行为与旧管线一致（零回归）。"""
    source = tmp_path / "plain.png"
    _striped_source(source)
    generator = PillowThumbnailGenerator(ThumbnailCache(tmp_path / "thumbs"))

    result = generator.generate(source, 256)

    with Image.open(result) as thumb:
        assert thumb.size == (4, 2)


def test_render_version_change_misses_legacy_cache_entries(tmp_path: Path) -> None:
    """缓存版本（P1 RENDER_VERSION=2）：旧 key 公式生成的条目永不命中，按需重生成。"""
    cache = ThumbnailCache(tmp_path / "thumbs")
    source = tmp_path / "photo.png"
    _striped_source(source)
    generator = PillowThumbnailGenerator(cache)
    current = generator.generate(source, 256)
    assert current.exists()

    # 旧公式（无渲染版本段）的 key 与新 key 必然不同。
    stat = source.stat()
    legacy_key = hashlib.sha256(
        f"{source.resolve(strict=False)}|256|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8"),
    ).hexdigest()[:24]
    assert legacy_key != current.stem
    legacy_file = cache.root / f"{legacy_key}.png"
    legacy_file.write_bytes(b"legacy-pixel junk")

    # 旧条目在场也不命中——生成器走新 key 路径（不返回、不覆盖遗留文件）。
    again = generator.generate(source, 256)
    assert again == current
    assert again != legacy_file
    assert legacy_file.read_bytes() == b"legacy-pixel junk"

    # 遗留条目成为孤儿，由既有 cleanup 服务清理。
    keep = {cache.compute_key(source, 256)}
    removed, retained = cache.cleanup(keep, dry_run=False)
    assert removed == 1 and not legacy_file.exists()
    assert current.exists()


def test_render_version_constant_is_bumped_for_exif_upright() -> None:
    """P1 渲染语义变更必须伴随版本提升：RENDER_VERSION 固定为 2。"""
    assert RENDER_VERSION == 2
