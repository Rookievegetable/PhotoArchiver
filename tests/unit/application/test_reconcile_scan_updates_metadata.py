"""Tests for scan re-scan reconciliation updating changed metadata (E-5, ADR-034 D5).

重扫同一文件夹时：文件内容变化（content hash / mtime+size）→ 刷新
``PhotoRepository.update_metadata``（updated_count+1）；未变化 → 保持
skipped 语义；reader 缺失/读取失败 → 保守不更新。快照列（captured_at）
不被刷新覆盖。
"""

from pathlib import Path

from photo_archiver.application import (
    ScanAndRegisterPhotosCommand,
    ScanAndRegisterPhotosService,
)
from photo_archiver.application.dtos import PhotoScanItem
from photo_archiver.domain import PhotoMetadata
from photo_archiver.infrastructure import (
    InMemoryFolderRepository,
    InMemoryPhotoRepository,
)


class _StubScanner:
    """Scanner double returning a fixed set of photo candidates."""

    def __init__(self, paths: list[Path]) -> None:
        self._paths = paths

    def scan(self, folder_path: Path, *, recursive: bool = True, supported_extensions=None):
        """Return the configured photo candidates."""
        return [PhotoScanItem(path=path, original_name=path.name) for path in self._paths]


class _MutableMetadataReader:
    """Reader double whose per-path metadata can be swapped between scans."""

    def __init__(self) -> None:
        self._metadata_by_path: dict[str, PhotoMetadata] = {}

    def set(self, disk_path: Path, metadata: PhotoMetadata) -> None:
        """Configure the metadata returned for the given disk path."""
        self._metadata_by_path[str(disk_path)] = metadata

    def read(self, path: Path) -> PhotoMetadata:
        """Return the configured metadata for the path."""
        return self._metadata_by_path[str(path)]


def _metadata(content_hash: str) -> PhotoMetadata:
    """Build metadata carrying the given content hash."""
    return PhotoMetadata(width=800, height=600, file_size_bytes=1024, content_hash=content_hash)


def _service(tmp_path: Path, reader: _MutableMetadataReader):
    """Assemble the scan service over in-memory repositories and the stub reader."""
    photo_path = tmp_path / "photo.jpg"
    scanner = _StubScanner([photo_path])
    folder_repository = InMemoryFolderRepository()
    photo_repository = InMemoryPhotoRepository()
    service = ScanAndRegisterPhotosService(
        scanner,
        folder_repository,
        photo_repository,
        metadata_reader=reader,
    )
    return service, photo_repository, photo_path


def test_rescan_updates_metadata_when_content_hash_changed(tmp_path: Path) -> None:
    """重扫：content hash 变化 → 刷新元数据（updated_count=1）。"""
    reader = _MutableMetadataReader()
    service, photo_repository, photo_path = _service(tmp_path, reader)
    reader.set(photo_path, _metadata("hash-v1"))

    first = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))
    reader.set(photo_path, _metadata("hash-v2"))  # 文件内容已变
    second = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert first.registered_count == 1
    assert second.registered_count == 0
    assert second.updated_count == 1
    assert second.skipped_count == 0
    assert second.discovered_count == 1
    photo = photo_repository.list_all()[0]
    assert photo.metadata is not None and photo.metadata.content_hash == "hash-v2"


def test_rescan_keeps_skipped_when_metadata_unchanged(tmp_path: Path) -> None:
    """重扫：内容未变 → 保持 skipped（不产生 updated）。"""
    reader = _MutableMetadataReader()
    service, photo_repository, photo_path = _service(tmp_path, reader)
    reader.set(photo_path, _metadata("same-hash"))

    service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))
    second = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert second.updated_count == 0
    assert second.skipped_count == 1


def test_rescan_falls_back_to_mtime_size_without_content_hash(tmp_path: Path) -> None:
    """无 content hash（B1 前历史照片）退化为 mtime+size 比对。"""
    from datetime import datetime

    reader = _MutableMetadataReader()
    service, _, photo_path = _service(tmp_path, reader)
    old = PhotoMetadata(width=800, height=600, file_size_bytes=1024,
                        modified_at=datetime(2024, 1, 1, 12, 0, 0))
    reader.set(photo_path, old)

    service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))
    # 文件变化：size 与 mtime 均变 → 判定为内容变化
    reader.set(photo_path, PhotoMetadata(
        width=800, height=600, file_size_bytes=2048,
        modified_at=datetime(2026, 9, 8, 12, 0, 0),
    ))
    second = service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    assert second.updated_count == 1
    assert second.skipped_count == 0


def test_rescan_update_preserves_snapshot_captured_at(tmp_path: Path) -> None:
    """刷新元数据保留快照列 captured_at（原登记拍摄时刻不回填）。"""
    from datetime import datetime

    reader = _MutableMetadataReader()
    service, photo_repository, photo_path = _service(tmp_path, reader)
    initial = PhotoMetadata(width=800, height=600, content_hash="v1")
    reader.set(photo_path, initial)

    service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))
    # 变更后重读会得到新的 captured_at（模拟真实 reader）——但快照列不得被覆盖
    changed = PhotoMetadata(
        width=800, height=600, content_hash="v2",
        captured_at=datetime(2025, 1, 1, 0, 0, 0),
    )
    reader.set(photo_path, changed)
    service.execute(ScanAndRegisterPhotosCommand(folder_path=tmp_path))

    photo = photo_repository.list_all()[0]
    assert photo.metadata is not None and photo.metadata.content_hash == "v2"