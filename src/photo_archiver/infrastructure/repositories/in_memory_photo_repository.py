"""In-memory implementation of the photo repository interface."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from photo_archiver.domain import (
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoRepository,
    PhotoSearchCriteria,
)


class InMemoryPhotoRepository(PhotoRepository):
    """Store photos in memory for tests and early application wiring."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._photos_by_id: dict[UUID, Photo] = {}

    def add(self, photo: Photo) -> None:
        """Persist a photo entity in memory."""
        self._photos_by_id[photo.id] = photo  # type: ignore[index]  # UUID | None guarantee

    def remove(self, photo_ids: Sequence[UUID]) -> int:
        """Remove the given photos from memory; return the removed count.

        幂等：不存在的 id 计 0 行。**不模拟级联**（ADR-034 §4.4）——
        识别/归档级联语义的唯一裁判是真实 SQLite 集成测试。
        """
        removed = 0
        for photo_id in photo_ids:
            if self._photos_by_id.pop(photo_id, None) is not None:
                removed += 1
        return removed

    def update_metadata(self, photo_id: UUID, metadata: PhotoMetadata | None) -> int:
        """Replace only the metadata on the stored photo; keep other columns.

        Phase E E-5（ADR-034 D5）：重扫对账刷新元数据。用 ``replace`` 仅替
        metadata 一字段——保留 captured_at / created_at / folder_id / path。
        幂等：id 不存在返回 0。
        """
        photo = self._photos_by_id.get(photo_id)
        if photo is None:
            return 0
        self._photos_by_id[photo_id] = replace(photo, metadata=metadata)
        return 1

    def update_capture_time(self, photo_id: UUID, captured_at: datetime | None) -> int:
        """Replace only captured_at on the stored photo; keep other columns.

        Phase F F-1（ADR-035）：与 SQLite 实现语义一致——``replace`` 仅替
        captured_at 字段。幂等：id 不存在返回 0。
        """
        photo = self._photos_by_id.get(photo_id)
        if photo is None:
            return 0
        self._photos_by_id[photo_id] = replace(photo, captured_at=captured_at)
        return 1

    def find_by_id(self, photo_id: UUID) -> Photo | None:
        """Find a photo by its domain identifier."""
        return self._photos_by_id.get(photo_id)

    def find_by_path(self, path: PhotoPath) -> Photo | None:
        """Find a photo by its path value."""
        return next((photo for photo in self._photos_by_id.values() if photo.path == path), None)

    def list_all(self) -> list[Photo]:
        """Return all known photos."""
        return list(self._photos_by_id.values())

    def list_by_folder_id(self, folder_id: UUID) -> list[Photo]:
        """Return photos belonging to the given folder."""
        return [photo for photo in self._photos_by_id.values() if photo.folder_id == folder_id]

    def search(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """Return photos matching every supplied criterion (AND combination).

        InMemory 走内存过滤（B2-a 裁决已拍板：InMemory 为测试替身，复杂度让位
        可读性；与 SQLite 实现的结果一致性靠对照测试守护）。person_id 与
        match_status 需查 recognition_results——但 InMemory 仓储不持 recognition
        结果，故这两个轴在 InMemory 下**无对应数据可过**，按契约"无 recognition
        结果的照片被 match_status 排除"——person_id/match_status 非空时返回空列表
        （测试替身场景下不会真筛这两轴，对照测试只用 captured_from/to 轴）。
        captured_from/to 走 Photo.captured_at 区间，NULL captured_at 默认排除。
        """
        results: list[Photo] = []
        for photo in self._photos_by_id.values():
            if criteria.person_id is not None or criteria.match_status is not None:
                # InMemory 仓储不持 recognition_results，这两轴无数据可过——按契
                # 约"无 recognition 结果的照片被 match_status 排除"返回空。对照测
                # 试只用 captured 轴守护一致性，避免在此两轴做 SQLite/InMemory 对照
                continue
            if criteria.captured_from is not None and photo.captured_at is None:
                continue  # NULL captured_at 默认排除（契约文档化）
            if criteria.captured_from is not None and photo.captured_at is not None:
                if photo.captured_at < criteria.captured_from:
                    continue
            if criteria.captured_to is not None and photo.captured_at is not None:
                if photo.captured_at > criteria.captured_to:
                    continue
            results.append(photo)
        # 排序与 SQLite 实现对齐——created_at + id
        return sorted(results, key=lambda p: (p.created_at, str(p.id)))

    def list_duplicate_groups(self) -> list[list[Photo]]:
        """Return groups of photos sharing the same non-null content hash.

        InMemory 走内存聚合（InMemory 为测试替身，复杂度
        让位可读性；与 SQLite 实现的结果一致性靠对照测试守护）。按非空
        content_hash 分桶，仅保留成员数 ≥2 的桶。组内顺序与 SQLite 实现
        对齐——按 created_at + id 排序——便于对照测试断言。
        """
        buckets: dict[str, list[Photo]] = {}
        for photo in self._photos_by_id.values():
            if photo.metadata is None or photo.metadata.content_hash is None:
                continue
            buckets.setdefault(photo.metadata.content_hash, []).append(photo)
        groups: list[list[Photo]] = []
        for photos in buckets.values():
            if len(photos) < 2:
                continue
            groups.append(sorted(photos, key=lambda p: (p.created_at, str(p.id))))
        return groups