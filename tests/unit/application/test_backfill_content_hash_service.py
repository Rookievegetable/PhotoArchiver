"""Tests for BackfillContentHashService one-time backfill (B1-a 裁决已拍板).

回填链路：取所有 NULL 哈希照片 → 重读元数据（含算哈希）→ 写回仓储。
跳过源文件已删者；reader 异常降级计数不中断整批。Idempotent。
"""

from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from photo_archiver.application import BackfillContentHashService
from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.infrastructure import (
    InMemoryPhotoRepository,
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.image import ContentHashCalculator


def _make_photo(name: str, content_hash: str | None, path: Path) -> Photo:
    """Build a Photo with explicit filesystem path and optional hash."""
    return Photo(
        path=PhotoPath(raw_path=path, base=PhotoPathBase.ABSOLUTE),
        folder_id=None,
        metadata=PhotoMetadata(
            content_hash=content_hash,
            modified_at=datetime(2026, 8, 1),
            captured_at=datetime(2026, 8, 1),
        ),
        original_name=name,
        captured_at=datetime(2026, 8, 1),
    )


def _make_jpg(path: Path) -> None:
    """Write a minimal valid JPG so Pillow can open it."""
    from PIL import Image

    Image.new("RGB", (120, 80), color="white").save(path)


def test_backfill_empty_repository_is_noop() -> None:
    """空仓储回填为 no-op——scanned=0 且 succeeded=True。"""
    repo = InMemoryPhotoRepository()
    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    service = BackfillContentHashService(repo, reader)

    result = service.execute()

    assert result.scanned == 0
    assert result.backfilled == 0
    assert result.succeeded


def test_backfill_all_already_hashed_is_noop(tmp_path: Path) -> None:
    """全已哈希仓储回填为 no-op——idempotent 重跑契约。"""
    a = tmp_path / "a.jpg"
    _make_jpg(a)
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", "already_set", a))
    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    service = BackfillContentHashService(repo, reader)

    result = service.execute()

    assert result.scanned == 0
    assert result.backfilled == 0


def test_backfill_fills_null_hash_photos(tmp_path: Path) -> None:
    """NULL 哈希照片经回填后 content_hash 非空——主成功路径。"""
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_jpg(a)
    _make_jpg(b)
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", None, a))
    repo.add(_make_photo("b", None, b))
    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    service = BackfillContentHashService(repo, reader)

    result = service.execute()

    assert result.scanned == 2
    assert result.backfilled == 2
    assert result.succeeded
    refreshed_a = repo.find_by_path(PhotoPath(raw_path=a, base=PhotoPathBase.ABSOLUTE))
    refreshed_b = repo.find_by_path(PhotoPath(raw_path=b, base=PhotoPathBase.ABSOLUTE))
    assert refreshed_a is not None and refreshed_a.metadata is not None
    assert refreshed_b is not None and refreshed_b.metadata is not None
    assert refreshed_a.metadata.content_hash is not None
    assert refreshed_b.metadata.content_hash is not None
    # 同字节 JPG 应产出同哈希——回填后即可纳入查重
    assert refreshed_a.metadata.content_hash == refreshed_b.metadata.content_hash


def test_backfill_skips_missing_source_files(tmp_path: Path) -> None:
    """源文件已删者跳过计数——skipped_missing 不中断整批。"""
    a = tmp_path / "a.jpg"
    missing = tmp_path / "missing.jpg"
    _make_jpg(a)
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", None, a))
    repo.add(_make_photo("historic", None, missing))  # 文件不存在
    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    service = BackfillContentHashService(repo, reader)

    result = service.execute()

    assert result.scanned == 2
    assert result.backfilled == 1
    assert result.skipped_missing == 1
    assert result.succeeded


def test_backfill_mixed_null_and_existing_hashes(tmp_path: Path) -> None:
    """混合 NULL+已哈希：仅 NULL 者被回填，已哈希者不动。"""
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_jpg(a)
    _make_jpg(b)
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", None, a))
    repo.add(_make_photo("b", "already_set", b))
    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    service = BackfillContentHashService(repo, reader)

    result = service.execute()

    assert result.scanned == 1  # 仅 NULL 者入候选
    assert result.backfilled == 1
    refreshed_b = repo.find_by_path(PhotoPath(raw_path=b, base=PhotoPathBase.ABSOLUTE))
    assert refreshed_b is not None and refreshed_b.metadata is not None
    assert refreshed_b.metadata.content_hash == "already_set"  # 已哈希者未被覆盖


def test_backfill_idempotent_on_second_run(tmp_path: Path) -> None:
    """重跑回填是 no-op——首次填完后第二次 scanned=0。"""
    a = tmp_path / "a.jpg"
    _make_jpg(a)
    repo = InMemoryPhotoRepository()
    repo.add(_make_photo("a", None, a))
    reader = PillowPhotoMetadataReader(content_hasher=ContentHashCalculator())
    service = BackfillContentHashService(repo, reader)

    first = service.execute()
    second = service.execute()

    assert first.backfilled == 1
    assert second.scanned == 0
    assert second.backfilled == 0
