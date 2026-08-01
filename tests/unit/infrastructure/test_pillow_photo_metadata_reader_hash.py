"""Tests for PillowPhotoMetadataReader content hash wiring (B1 重复图片检测).

落 B1-c 裁决已拍板：reader 可选注入 ContentHashCalculator，注入时同一 pass
内算 SHA-256 填 PhotoMetadata.content_hash，未注入时保持向后兼容。
"""

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from photo_archiver.infrastructure import PillowPhotoMetadataReader
from photo_archiver.infrastructure.image import ContentHashCalculator


def _make_jpg(path: Path) -> None:
    """Write a minimal valid JPG so Pillow can open it."""
    from PIL import Image

    Image.new("RGB", (120, 80), color="white").save(path)


def test_reader_without_hasher_leaves_content_hash_none(tmp_path: Path) -> None:
    """未注入 hasher 的 reader 保持历史行为——content_hash 为 None（向后兼容）。"""
    source = tmp_path / "a.jpg"
    _make_jpg(source)

    metadata = PillowPhotoMetadataReader().read(source)

    assert metadata.content_hash is None


def test_reader_with_hasher_fills_content_hash(tmp_path: Path) -> None:
    """注入 hasher 的 reader 在同一 pass 内算 SHA-256 填 content_hash。"""
    source = tmp_path / "a.jpg"
    _make_jpg(source)

    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    metadata = reader.read(source)

    assert metadata.content_hash is not None
    assert len(metadata.content_hash) == 64  # SHA-256 hex digest length


def test_reader_with_hasher_same_bytes_same_hash(tmp_path: Path) -> None:
    """相同字节内容的不同路径照片产出相同哈希——这是查重语义的根基。"""
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_jpg(a)
    _make_jpg(b)

    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    meta_a = reader.read(a)
    meta_b = reader.read(b)

    assert meta_a.content_hash == meta_b.content_hash


def test_reader_with_hasher_different_bytes_different_hash(tmp_path: Path) -> None:
    """不同字节内容的照片产出不同哈希——避免误判为重复。"""
    from PIL import Image

    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    Image.new("RGB", (120, 80), color="white").save(a)
    Image.new("RGB", (120, 80), color="black").save(b)

    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    meta_a = reader.read(a)
    meta_b = reader.read(b)

    assert meta_a.content_hash != meta_b.content_hash


def test_reader_hasher_failure_leaves_hash_none_but_metadata_intact(tmp_path: Path) -> None:
    """哈希 I/O 异常不中断元数据读取——降级为 content_hash=None + warning。"""

    class _FailingHasher(ContentHashCalculator):
        def calculate(self, source: Path) -> str:  # noqa: ARG002
            raise OSError("simulated hash failure")

    source = tmp_path / "a.jpg"
    _make_jpg(source)

    reader = PillowPhotoMetadataReader(content_hasher=_FailingHasher())
    metadata = reader.read(source)

    assert metadata.content_hash is None
    # 其他元数据仍就绪——扫描整批不被哈希异常拖崩
    assert metadata.width == 120
    assert metadata.height == 80


def test_reader_hasher_missing_file_returns_none(tmp_path: Path) -> None:
    """源文件在算哈希前已删（FileNotFoundError）降级为 None 而非抛错。"""

    class _ExplodingHasher(ContentHashCalculator):
        def calculate(self, source: Path) -> str:
            raise FileNotFoundError(source)

    source = tmp_path / "a.jpg"
    _make_jpg(source)

    reader = PillowPhotoMetadataReader(content_hasher=_ExplodingHasher())
    metadata = reader.read(source)

    assert metadata.content_hash is None
