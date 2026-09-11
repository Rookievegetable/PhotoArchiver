"""Thumbnail cache cleanup service — ISSUE-023 (体检 N-8) end-to-end.

真实 SQLite 仓库 + 真实缓存目录：keep 集合 = 当前库内照片 × 当前渲染尺寸；
孤儿（含失联源文件的旧条目）按 dry-run 语义先报后删。
"""

from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from datetime import datetime

from photo_archiver.domain import Folder, Photo, PhotoPath, PhotoPathBase
from photo_archiver.infrastructure.image import ThumbnailCache


def _write_real_jpeg(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (4, 4), color=(90, 120, 200)).save(path, format="JPEG")


def test_cleanup_service_removes_orphans_keeps_live_entries(
    make_sqlite_context, tmp_path
) -> None:
    context = make_sqlite_context("thumb_cleanup.db", output_root=tmp_path / "out")
    cache_root = tmp_path / "out" / "thumbnails"
    cache = ThumbnailCache(cache_root)

    folder = Folder(path=PhotoPath("photos"), total_photos=1)
    context.repositories.folders.add(folder)
    source = tmp_path / "photos" / "one.jpg"
    source.parent.mkdir()
    _write_real_jpeg(source)
    # 生产扫描器注册的是绝对路径（缓存键因此包含绝对源路径）——与之一致。
    context.repositories.photos.add(
        Photo(
            path=PhotoPath(source, PhotoPathBase.ABSOLUTE),
            folder_id=folder.id,
            original_name="one.jpg",
            captured_at=datetime(2024, 1, 1, 8, 0, 0),
        )
    )

    live_key = cache.compute_key(source, 256)
    assert live_key is not None
    (cache_root / f"{live_key}.jpg").write_bytes(b"live")
    (cache_root / ("e" * 24 + ".jpg")).write_bytes(b"orphan")

    # Dry-run：只报不删（与 prune-missing 同语义）。
    result = context.services.cleanup_thumbnails.execute(dry_run=True)
    assert (result.removed, result.retained, result.dry_run) == (1, 1, True)
    assert (cache_root / ("e" * 24 + ".jpg")).exists()

    # Execute：孤儿删除，活条目保留。
    result = context.services.cleanup_thumbnails.execute(dry_run=False)
    assert (result.removed, result.retained, result.dry_run) == (1, 1, False)
    assert not (cache_root / ("e" * 24 + ".jpg")).exists()
    assert (cache_root / f"{live_key}.jpg").exists()


def test_cleanup_service_treats_missing_source_entries_as_orphans(
    make_sqlite_context, tmp_path
) -> None:
    """源文件已失联的照片：其旧缓存条目按孤儿处理（无 keep 键产生）。"""
    context = make_sqlite_context("thumb_cleanup_missing.db", output_root=tmp_path / "out")
    cache_root = tmp_path / "out" / "thumbnails"

    orphan = cache_root / ("d" * 24 + ".jpg")
    orphan.write_bytes(b"orphan")

    result = context.services.cleanup_thumbnails.execute(dry_run=False)

    assert result.removed == 1
    assert not orphan.exists()
