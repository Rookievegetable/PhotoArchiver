"""In-memory implementation of the photo repository interface."""

from uuid import UUID

from photo_archiver.domain import Photo, PhotoPath, PhotoRepository


class InMemoryPhotoRepository(PhotoRepository):
    """Store photos in memory for tests and early application wiring."""

    def __init__(self) -> None:
        """Initialize empty in-memory storage."""
        self._photos_by_id: dict[UUID, Photo] = {}

    def add(self, photo: Photo) -> None:
        """Persist a photo entity in memory."""
        self._photos_by_id[photo.id] = photo  # type: ignore[index]  # UUID | None guarantee

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