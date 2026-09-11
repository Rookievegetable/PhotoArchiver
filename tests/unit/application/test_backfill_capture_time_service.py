"""Tests for BackfillCaptureTimeService (Phase F F-1, ADR-035).

Issue-019 后历史照片拍摄时刻一次性纠错：全量重读 → 差异 →
``update_capture_time`` 对齐；dry-run 默认只读；逐文件异常降级计数。
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.application import BackfillCaptureTimeService
from photo_archiver.application.commands import BackfillCaptureTimeCommand
from photo_archiver.domain import Photo, PhotoMetadata, PhotoPath, PhotoPathBase
from photo_archiver.infrastructure import InMemoryPhotoRepository


class _MutableMetadataReader:
    """Reader double whose per-path metadata can be configured."""

    def __init__(self) -> None:
        self._metadata_by_path: dict[str, PhotoMetadata] = {}
        self._failing: set[str] = set()

    def set(self, disk_path: Path, metadata: PhotoMetadata) -> None:
        """Configure the metadata returned for the given disk path."""
        self._metadata_by_path[str(disk_path)] = metadata

    def fail_for(self, disk_path: Path) -> None:
        """Configure the reader to raise for the given disk path."""
        self._failing.add(str(disk_path))

    def read(self, path: Path) -> PhotoMetadata:
        """Return the configured metadata or raise for failing paths."""
        if str(path) in self._failing:
            raise ValueError("corrupt image")
        return self._metadata_by_path[str(path)]


def _build(tmp_path: Path, reader: _MutableMetadataReader):
    """Register one photo with the legacy captured_at; return (service, repo, path)."""
    repository = InMemoryPhotoRepository()
    disk_path = tmp_path / "photo.jpg"
    disk_path.write_bytes(b"stub")
    photo = Photo(
        path=PhotoPath(raw_path=disk_path, base=PhotoPathBase.ABSOLUTE),
        original_name="photo.jpg",
        metadata=PhotoMetadata(width=800, height=600),
        captured_at=datetime(2023, 1, 1, 0, 0, 0),  # 旧 reader 的 mtime 冒名值
    )
    repository.add(photo)
    service = BackfillCaptureTimeService(repository, reader)
    return service, repository, disk_path, photo


def test_backfill_updates_differing_capture_time(tmp_path: Path) -> None:
    """登记值与重读值不同 → --execute 更新（仓储 captured_at 纠错）。"""
    reader = _MutableMetadataReader()
    service, repository, disk_path, photo = _build(tmp_path, reader)
    fresh_capture = datetime(2024, 7, 13, 16, 42, 1)
    reader.set(disk_path, PhotoMetadata(width=800, height=600, captured_at=fresh_capture))

    result = service.execute(BackfillCaptureTimeCommand(dry_run=False))

    assert result.scanned == 1
    assert result.updated == 1
    assert result.succeeded is True
    refreshed = repository.find_by_id(photo.id)
    assert refreshed is not None and refreshed.captured_at == fresh_capture
    assert refreshed.metadata is not None and refreshed.metadata.width == 800  # metadata 不动


def test_backfill_dry_run_counts_without_writing(tmp_path: Path) -> None:
    """默认 dry-run：报差异计数，绝不写库。"""
    reader = _MutableMetadataReader()
    service, repository, disk_path, photo = _build(tmp_path, reader)
    reader.set(disk_path, PhotoMetadata(width=800, height=600, captured_at=datetime(2024, 7, 13)))

    result = service.execute()  # 无参 = 默认 dry-run

    assert result.would_update == 1
    assert result.updated == 0
    assert repository.find_by_id(photo.id).captured_at == datetime(2023, 1, 1, 0, 0, 0)  # 未写


def test_backfill_counts_unchanged_and_missing_and_failed(tmp_path: Path) -> None:
    """unchanged / skipped_missing / failed 各自如实计数，不中断整批。"""
    reader = _MutableMetadataReader()
    service, repository, disk_path, photo = _build(tmp_path, reader)
    reader.set(disk_path, PhotoMetadata(width=800, height=600, captured_at=datetime(2023, 1, 1)))  # 同值
    reader.fail_for(disk_path)  # 同一路径既配置值又失败——失败优先

    result = service.execute(BackfillCaptureTimeCommand(dry_run=False))

    assert result.failed == 1
    assert result.unchanged == 0
    assert result.succeeded is False

    # 文件缺失场景：新建一个登记但文件不存在
    ghost = Photo(
        path=PhotoPath(raw_path=tmp_path / "ghost.jpg", base=PhotoPathBase.ABSOLUTE),
        original_name="ghost.jpg",
    )
    repository.add(ghost)
    result2 = service.execute(BackfillCaptureTimeCommand(dry_run=False))
    assert result2.skipped_missing == 1  # ghost 的文件不存在
    assert result2.failed == 1


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    """纠错后重跑：差异归零（unchanged=1，updated=0）。"""
    reader = _MutableMetadataReader()
    service, repository, disk_path, photo = _build(tmp_path, reader)
    fresh_capture = datetime(2024, 7, 13, 16, 42, 1)
    reader.set(disk_path, PhotoMetadata(width=800, height=600, captured_at=fresh_capture))

    service.execute(BackfillCaptureTimeCommand(dry_run=False))
    second = service.execute(BackfillCaptureTimeCommand(dry_run=False))

    assert second.updated == 0
    assert second.would_update == 0
    assert second.unchanged == 1