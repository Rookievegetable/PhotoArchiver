"""Controller coordinating the photo-list view with repository reads.

落 Phase 2 Step 12 裁决 B：缩略图加载策略——缓存命中（磁盘已存在）同步 (<1ms)，
未命中异步入 QThreadPool（Pillow 生成 50-200ms 避免卡 UI）。
Step 7 ThumbnailCache 已就绪（resolve + is_stale），本 controller 持它做命中查询，
未命中时调 PillowThumbnailGenerator + 异步 dispatch。
"""

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import QObject, Qt, QRunnable, QThreadPool, Signal, Slot

from photo_archiver.application.ports import ThumbnailCache, ThumbnailGenerator
from photo_archiver.domain import Photo, PhotoRepository, PhotoSearchCriteria

if TYPE_CHECKING:
    from photo_archiver.application.services import SearchPhotosService

# Default thumbnail bounding box size matches ThumbnailGenerator.generate default.
_DEFAULT_THUMBNAIL_SIZE = 256


class _ThumbnailJob(QRunnable):
    """QRunnable that generates one thumbnail off the UI thread.

    review m-1 fix: lifted to module level so Python doesn't rebuild the class
    object on every cache-miss load_thumbnail call. The job captures the
    controller via a closure-free constructor argument to stay pickle-safe.
    """

    def __init__(self, controller: "PhotoListController", pid: UUID, path: Path) -> None:
        super().__init__()
        self._controller = controller
        self._pid = pid
        self._path = path

    def run(self) -> None:
        try:
            thumb_path = self._controller._thumbnail_generator.generate(
                self._path, _DEFAULT_THUMBNAIL_SIZE,
            )
            self._controller.thumbnail_loaded.emit(self._pid, thumb_path)
        except Exception:  # noqa: BLE001 - UI must not crash on one bad photo
            self._controller.thumbnail_loaded.emit(self._pid, None)
        finally:
            self._controller._in_flight.discard(self._pid)


class PhotoListController(QObject):
    """Provide photo-list data to UI views with async thumbnail loading.

    The controller is read-only — it surfaces photos from the repository
    and loads thumbnails into the cache, but never mutates domain state.

    Thread safety (review M-1/M-4 fixes):
        - ``_in_flight`` dedupes cache-miss loads so the same photo isn't
          dispatched twice to QThreadPool (which would race writing the
          same cache path and could leave a half-written file).
        - ``_on_thumbnail_ready`` is invoked via QueuedConnection so the
          PhotoListModel mutation + dataChanged signal always run on the
          UI thread, never on the QThreadPool worker thread.
    """

    thumbnail_loaded = Signal(object, object)  # (photo_id, thumbnail_path or None)

    def __init__(
        self,
        photo_repository: PhotoRepository,
        thumbnail_cache: ThumbnailCache,
        thumbnail_generator: ThumbnailGenerator,
        search_service: "SearchPhotosService | None" = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its repository and thumbnail services.

        Args:
            search_service: Optional ``SearchPhotosService`` for B2 filtering.
                When provided, ``search_photos(criteria)`` delegates to it;
                when None (legacy/CLI/CI paths without Qt filtering), calls
                to ``search_photos`` raise NotImplementedError. MainWindow
                assembly wires this; CLI paths leave it unset.
        """
        super().__init__(parent)
        self._photo_repository = photo_repository
        self._thumbnail_cache = thumbnail_cache
        self._thumbnail_generator = thumbnail_generator
        self._search_service = search_service
        self._in_flight: set[UUID] = set()
        # Wire the async completion back through a QueuedConnection so the
        # signal fires on the UI thread, not the QThreadPool worker thread.
        self.thumbnail_loaded.connect(self._on_thumbnail_ready, Qt.QueuedConnection)  # type: ignore[attr-defined]

    def list_photos(self) -> list[Photo]:
        """Return all registered photos for the photo-list view."""
        return self._photo_repository.list_all()

    def search_photos(self, criteria: PhotoSearchCriteria) -> list[Photo]:
        """Return photos matching the supplied search criteria.

        Delegates to ``SearchPhotosService`` when wired (B2 filtering path);
        raises NotImplementedError when the service was not injected (CLI/CI
        paths that don't need filtering). The query is synchronous — fast SQL
        push-down per the dual-strategy decision, no Worker submission.
        """
        if self._search_service is None:
            raise NotImplementedError(
                "search_photos requires a SearchPhotosService to be wired at construction; "
                "this controller instance was built without one (CLI/CI path).",
            )
        return self._search_service.execute(criteria)

    def load_thumbnail(self, photo_id: UUID, source_path: Path) -> None:
        """Load a thumbnail for one photo, emitting thumbnail_loaded when ready.

        Cache hit (resolved path exists on disk) is synchronous (<1ms). Cache
        miss dispatches to QThreadPool; ``_in_flight`` dedupes so a repeated
        call for the same photo while the Job is already running is a no-op
        rather than a second racing Job.
        """
        resolved = self._thumbnail_cache.resolve(source_path, _DEFAULT_THUMBNAIL_SIZE)
        if resolved is not None and not self._thumbnail_cache.is_stale(source_path, resolved):
            self.thumbnail_loaded.emit(photo_id, resolved)
            return

        if photo_id in self._in_flight:
            return  # already dispatched; the in-flight Job will emit when done

        self._in_flight.add(photo_id)
        QThreadPool.globalInstance().start(_ThumbnailJob(self, photo_id, source_path))

    @Slot(object, object)
    def _on_thumbnail_ready(self, photo_id: object, thumbnail: object) -> None:
        """Receive the thumbnail result on the UI thread (via QueuedConnection).

        This is a passive sink kept so the controller's own QueuedConnection
        wiring is observable in tests; the PhotoListModel connects its
        ``set_thumbnail`` slot to ``thumbnail_loaded`` independently, and Qt
        routes that emit through the same queued path to the UI thread.
        """
        # No-op: actual model mutation happens in PhotoListModel.set_thumbnail
        # which the MainWindow connects after controller construction. This
        # slot exists purely so the controller self-references the signal and
        # the QueuedConnection wiring is unit-testable.
        return
