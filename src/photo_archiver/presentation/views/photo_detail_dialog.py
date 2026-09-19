"""Read-only photo detail dialog (Batch 4).

Larger preview plus the archival context of one photo — original name,
path, capture time and the recognition/archival badge. Data comes from the
already-loaded Photo entity and the cached thumbnail file; nothing here
performs synchronous disk IO beyond the tiny cached thumbnail decode, and
every field degrades gracefully when absent (no data → "未知" line, no
thumbnail → an explicit pending note).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import Photo
from photo_archiver.presentation import ui_text as text

_PREVIEW_HEIGHT = 320


class PhotoDetailDialog(QDialog):
    """Show one photo's read-only details; double-click entry in the library."""

    def __init__(
        self,
        photo: Photo,
        badge: str | None = None,
        thumbnail_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Compose the preview and metadata rows from already-loaded data."""
        super().__init__(parent)
        self.setWindowTitle(text.PHOTO_DETAIL_TITLE)
        layout = QVBoxLayout(self)

        preview = QLabel(self)
        pixmap = QPixmap()
        if thumbnail_path is not None:
            pixmap.load(str(thumbnail_path))
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(
                _PREVIEW_HEIGHT, Qt.TransformationMode.SmoothTransformation,
            )
            preview.setPixmap(scaled)
        else:
            preview.setText(text.PHOTO_DETAIL_THUMB_PENDING)
        layout.addWidget(preview)

        name = photo.original_name or photo.path.raw_path
        layout.addWidget(QLabel(text.PHOTO_DETAIL_NAME.format(name=name), self))
        layout.addWidget(QLabel(
            text.PHOTO_DETAIL_PATH.format(path=photo.path.raw_path), self,
        ))
        if photo.captured_at is not None:
            captured = text.PHOTO_DETAIL_CAPTURED.format(
                time=photo.captured_at.strftime("%Y-%m-%d %H:%M"),
            )
        else:
            captured = text.PHOTO_DETAIL_CAPTURED_UNKNOWN
        layout.addWidget(QLabel(captured, self))
        status = text.PHOTO_DETAIL_STATUS.format(
            badge=badge if badge else text.FILTER_STATUS_UNMATCHED,
        )
        layout.addWidget(QLabel(status, self))
        layout.addStretch()
