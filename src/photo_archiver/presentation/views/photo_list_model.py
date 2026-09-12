"""Photo list model for the main window's central QListView.

Holds a list of Photo aggregates surfaced by PhotoListController and exposes
per-row data (thumbnail path, original name, photo id) to
PhotoThumbnailDelegate, which paints the cached thumbnail with the name.
Thumbnails are loaded lazily by the controller and pushed into the model via
set_thumbnail so the model never does IO itself.
"""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from photo_archiver.domain import Photo

# Role constants exposed to the QListView delegate and tests. Numbers start
# above Qt.UserRole so we don't clobber Qt's own role slots.
THUMBNAIL_ROLE = Qt.UserRole + 1  # type: ignore[attr-defined]
ORIGINAL_NAME_ROLE = Qt.UserRole + 2  # type: ignore[attr-defined]
PHOTO_ID_ROLE = Qt.UserRole + 3  # type: ignore[attr-defined]
STATUS_BADGE_ROLE = Qt.UserRole + 4  # type: ignore[attr-defined]  # G-4 状态角标


class PhotoListModel(QAbstractListModel):
    """Expose a list of Photo aggregates as a Qt model for QListView."""

    def __init__(self, parent=None) -> None:
        """Initialize an empty model; photos loaded via load_photos."""
        super().__init__(parent)
        self._photos: list[Photo] = []
        # photo_id -> resolved thumbnail Path, populated by set_thumbnail.
        self._thumbnails: dict[UUID, Path | None] = {}
        # G-4：photo_id -> 角标文本（识别状态 · 归档），由 MainWindow 经
        # PhotoListController.status_badges 计算后注入。
        self._badges: dict[UUID, str] = {}

    def load_photos(self, photos: list[Photo]) -> None:
        """Replace the model's photos, emitting layout reset signals."""
        self.beginResetModel()
        self._photos = list(photos)
        self._thumbnails.clear()
        self._badges.clear()
        self.endResetModel()

    def set_thumbnail(self, photo_id: UUID, thumbnail: Path | None) -> None:
        """Cache a loaded thumbnail for the given photo and emit dataChanged.

        Called by PhotoListController.thumbnail_loaded slot so the QListView
        re-paints just the affected row(s). Finding the row by photo_id keeps
        the slot decoupled from model row indices.
        """
        self._thumbnails[photo_id] = thumbnail
        for row, photo in enumerate(self._photos):
            if photo.id == photo_id:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [THUMBNAIL_ROLE])
                return

    def set_status_badges(self, badges: dict[UUID, str]) -> None:
        """Install per-photo status badge texts (G-4) and repaint every row.

        Called by MainWindow right after ``load_photos``; the wholesale
        ``dataChanged`` is intentional — badges arrive as a batch computed
        from two repositories, so per-row deltas would cost more than one
        repaint pass.
        """
        self._badges = dict(badges)
        if self._photos:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._photos) - 1, 0),
                [STATUS_BADGE_ROLE],
            )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        """Return the number of photos; invalid parent per QAIM convention."""
        return 0 if parent.isValid() else len(self._photos)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[attr-defined,override]
        """Return the data for the given index and role.

        Qt.DisplayRole returns the original name as the row's visible label.
        THUMBNAIL_ROLE / ORIGINAL_NAME_ROLE / PHOTO_ID_ROLE return their
        respective fields for the delegate and tests.
        """
        if not index.isValid() or not (0 <= index.row() < len(self._photos)):
            return None
        photo = self._photos[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:  # type: ignore[attr-defined]
            return photo.original_name or photo.path.raw_path.name
        if role == ORIGINAL_NAME_ROLE:
            return photo.original_name or photo.path.raw_path.name
        if role == THUMBNAIL_ROLE:
            return self._thumbnails.get(photo.id)  # type: ignore[arg-type]  # UUID | None guarantee
        if role == PHOTO_ID_ROLE:
            return photo.id
        if role == STATUS_BADGE_ROLE:
            return self._badges.get(photo.id) if photo.id is not None else None
        return None
