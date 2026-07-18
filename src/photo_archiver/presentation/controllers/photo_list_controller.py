"""Controller coordinating the photo-list view with repository reads.

落 Phase 2 Step 12 裁决 B：缩略图加载策略——缓存命中（磁盘已存在）同步 (<1ms)，
未命中异步入 QThreadPool（Pillow 生成 50-200ms 避免卡 UI）。
Step 7 ThumbnailCache 已就绪（resolve + is_stale），本 controller 持它做命中查询，
未命中时调 PillowThumbnailGenerator + 异步 dispatch。
"""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, Signal

from photo_archiver.application.ports import ThumbnailGenerator
from photo_archiver.domain import Photo, PhotoRepository
from photo_archiver.infrastructure.image import ThumbnailCache

# Default thumbnail bounding box size matches ThumbnailGenerator.generate default.
_DEFAULT_THUMBNAIL_SIZE = 256


class PhotoListController(QObject):
    """Provide photo-list data to UI views with async thumbnail loading.

    The controller is read-only — it surfaces photos from the repository
    and loads thumbnails into the cache, but never mutates domain state.
    """

    thumbnail_loaded = Signal(object, object)  # (photo_id, thumbnail_path or None)

    def __init__(
        self,
        photo_repository: PhotoRepository,
        thumbnail_cache: ThumbnailCache,
        thumbnail_generator: ThumbnailGenerator,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its repository and thumbnail services.

        Args:
            photo_repository: Read source for Photo aggregates.
            thumbnail_cache: Path resolver + staleness check (Step 7).
            thumbnail_generator: Pillow-based generator for cache misses.
        """
        super().__init__(parent)
        self._photo_repository = photo_repository
        self._thumbnail_cache = thumbnail_cache
        self._thumbnail_generator = thumbnail_generator

    def list_photos(self) -> list[Photo]:
        """Return all registered photos for the photo-list view.

        Ordered by created_at DESC so recently-scanned photos surface first.
        For thousands of photos a paged variant should be added later; current
        scale is fine for a single list load.
        """
        return self._photo_repository.list_all()

    def load_thumbnail(self, photo_id: UUID, source_path: Path) -> None:
        """Load a thumbnail for one photo, emitting thumbnail_loaded when ready.

        Cache hit (resolved path exists on disk) is synchronous (<1ms) — the
        caller can call this in a tight loop over the visible photos without
        dispatching threads. Cache miss dispatches to QThreadPool for Pillow
        generation, keeping the UI thread free of 50-200ms Pillow work.
        """
        resolved = self._thumbnail_cache.resolve(source_path, _DEFAULT_THUMBNAIL_SIZE)
        if resolved is not None and not self._thumbnail_cache.is_stale(source_path, resolved):
            self.thumbnail_loaded.emit(photo_id, resolved)
            return

        # Cache miss — dispatch async. We do NOT block the UI thread on Pillow.
        from PySide6.QtCore import QRunnable, QThreadPool

        controller = self

        class _ThumbnailJob(QRunnable):
            """QRunnable that generates one thumbnail off the UI thread."""

            def __init__(self, pid: UUID, path: Path) -> None:
                super().__init__()
                self._pid = pid
                self._path = path

            def run(self) -> None:
                try:
                    thumb_path = controller._thumbnail_generator.generate(
                        self._path, _DEFAULT_THUMBNAIL_SIZE,
                    )
                    controller.thumbnail_loaded.emit(self._pid, thumb_path)
                except Exception:  # noqa: BLE001 - UI must not crash on one bad photo
                    controller.thumbnail_loaded.emit(self._pid, None)

        QThreadPool.globalInstance().start(_ThumbnailJob(photo_id, source_path))
