"""Photo list delegate — renders thumbnails with names (P0-2).

QStyledItemDelegate consuming :data:`PhotoListModel.THMUMBNAIL_ROLE` — the
consumer the design intended (the model docstring reserved the role for a
delegate) but that was never written: without it the default delegate renders
filenames only, and the whole thumbnail pipeline (generation → cache → async
load → model) is invisible to the user.

The Path → QPixmap conversion happens here in Presentation; Domain and
Application stay Qt-free. Pixmaps go through Qt's global ``QPixmapCache``
(keyed by resolved path) so repeated repaints don't re-read the disk while
eviction stays Qt-managed — no hand-rolled cache to leak.
"""

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap, QPixmapCache
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)

from photo_archiver.presentation.views.photo_list_model import STATUS_BADGE_ROLE, THUMBNAIL_ROLE

# The generation contract keeps thumbnails inside a 256px bounding box
# (PhotoListController); the DISPLAY cell shows them in a compact grid —
# the 256px source downscales on paint (SmoothTransformation).
_THUMBNAIL_BOX = 160
_TEXT_HEIGHT = 24
_PADDING = 6

_CACHE_KEY_PREFIX = "photo-thumbnail:"


class PhotoThumbnailDelegate(QStyledItemDelegate):
    """Paint each photo row as its cached thumbnail with the name beneath."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        """Draw the thumbnail (top, aspect-preserved) and the name (bottom).

        Rows whose thumbnail did not resolve (missing file, decode failure)
        fall back to the default text-only painting instead of failing.
        """
        thumbnail = self._load_pixmap(index.data(THUMBNAIL_ROLE))
        if thumbnail.isNull():
            super().paint(painter, option, index)  # type: ignore[arg-type]
            return

        # Keep the platform selection/hover styling for the row background.
        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, widget
        )

        painter.save()
        rect = option.rect
        image_box = QRect(
            rect.left(),
            rect.top(),
            rect.width(),
            min(_THUMBNAIL_BOX, max(1, rect.height() - _TEXT_HEIGHT)),
        )
        scaled = thumbnail.scaled(
            image_box.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(
            image_box.left() + (image_box.width() - scaled.width()) // 2,
            image_box.top() + (image_box.height() - scaled.height()) // 2,
            scaled,
        )

        # G-4：状态角标——识别状态 · 归档，右上角半透明小签（主题无关）。
        badge = index.data(STATUS_BADGE_ROLE)
        if badge:
            metrics = QFontMetrics(option.font)
            badge_text = str(badge)
            chip_width = metrics.horizontalAdvance(badge_text) + 2 * _PADDING
            chip_height = metrics.height() + 4
            chip = QRect(
                image_box.right() - chip_width,
                image_box.top() + 2,
                chip_width,
                chip_height,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.drawRoundedRect(chip, 4, 4)
            painter.setPen(QColor("white"))
            painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, badge_text)

        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        text_rect = QRect(
            rect.left() + _PADDING,
            image_box.bottom() + 1,
            rect.width() - 2 * _PADDING,
            _TEXT_HEIGHT,
        )
        elided = QFontMetrics(option.font).elidedText(
            str(name), Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(
            option.palette.color(option.palette.ColorRole.HighlightedText)
            if option.state & QStyle.StateFlag.State_Selected
            else option.palette.color(option.palette.ColorRole.Text)
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, elided)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # type: ignore[override]
        """Return a constant cell size — data-INDEPENDENT by design.

        缩略图经异步管线后到：若 sizeHint 依赖数据（无图时回退默认小尺寸），
        ``QListView.uniformItemSizes`` 会把首项的"未加载"尺寸锁死给全部单元
        （2026-09-06 桌面实测：73×18 坍缩）。恒定尺寸让缩略图到达前后布局
        稳定；无图回退绘制在同等矩形内照常工作。
        """
        return QSize(_THUMBNAIL_BOX + 2 * _PADDING, _THUMBNAIL_BOX + _TEXT_HEIGHT + _PADDING)

    def _load_pixmap(self, source: object) -> QPixmap:
        """Resolve the model's thumbnail path to a cached QPixmap.

        Returns a null QPixmap for anything that is not an existing file so
        callers can fall back to default painting.
        """
        if not isinstance(source, Path) or not source.is_file():
            return QPixmap()
        key = f"{_CACHE_KEY_PREFIX}{source.resolve(strict=False)}|{source.stat().st_mtime_ns}"
        pixmap = QPixmap()
        if not QPixmapCache.find(key, pixmap):
            pixmap = QPixmap(str(source))
            if not pixmap.isNull():
                QPixmapCache.insert(key, pixmap)
        return pixmap
