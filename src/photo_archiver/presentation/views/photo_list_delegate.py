"""Photo list delegate — renders thumbnails with names (P0-2).

QStyledItemDelegate consuming :data:`PhotoListModel.THMUMBNAIL_ROLE` — the
consumer the design intended (the model docstring reserved the role for a
delegate) but that was never written: without it the default delegate renders
filenames only, and the whole thumbnail pipeline (generation → cache → async
load → model) is invisible to the user.

2026-09-30 选中态优化：State_Selected 的单元格在缩略图上追加内缘描边
（palette Highlight）与左上角几何勾选章（Highlight 填充 + HighlightedText
折线对勾），文件名沿用 HighlightedText——三重反馈全部取自活调色板，本模块
不引入任何固定色值。无缩略图的行走平台 fallback 绘制（文档化降级，见
KNOWN 决策：不为异常路径重复实现选中视觉）。

The Path → QPixmap conversion happens here in Presentation; Domain and
Application stay Qt-free. Pixmaps go through Qt's global ``QPixmapCache``
(keyed by resolved path) so repeated repaints don't re-read the disk while
eviction stays Qt-managed — no hand-rolled cache to leak.
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPixmapCache,
    QPolygonF,
)
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

# 2026-09-30 选中态三重反馈：内缘描边 + 左上角几何勾选章 + 文件名高亮。
# 颜色一律取自 option.palette（活调色板），禁止硬编码 RGB——本机深色主题
# 与 CI 浅色调色板不同，固定色值必然跨平台失真（Stage 14-CI 同一契约）。
_SELECTION_STROKE_WIDTH = 2
_CHECK_BADGE_SIZE = 16
_CHECK_BADGE_MARGIN = 4

_CACHE_KEY_PREFIX = "photo-thumbnail:"


def name_color(palette: QPalette, selected: bool) -> QColor:
    """Return the filename color: HighlightedText when selected, else Text."""
    role = (
        palette.ColorRole.HighlightedText if selected else palette.ColorRole.Text
    )
    return palette.color(role)


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
        widget = option.widget  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
        style = widget.style() if widget is not None else QApplication.style()
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, widget
        )

        painter.save()
        rect = option.rect  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
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
        pixmap_rect = QRect(
            image_box.left() + (image_box.width() - scaled.width()) // 2,
            image_box.top() + (image_box.height() - scaled.height()) // 2,
            scaled.width(),
            scaled.height(),
        )
        painter.drawPixmap(pixmap_rect, scaled)

        # 选中态：内缘描边 + 左上角勾选章（仅 State_Selected，绘制顺序在
        # 缩略图之上、状态角标与文件名之前——后者各自重设画笔/画刷）。
        palette = option.palette  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
        selected = bool(option.state & QStyle.StateFlag.State_Selected)  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
        if selected:
            self._draw_selection_stroke(painter, palette, pixmap_rect)
            self._draw_check_badge(painter, palette, pixmap_rect)

        # G-4：状态角标——识别状态 · 归档，右上角半透明小签（主题无关）。
        badge = index.data(STATUS_BADGE_ROLE)
        if badge:
            metrics = QFontMetrics(option.font)  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
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
        elided = QFontMetrics(option.font).elidedText(  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
            str(name), Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(name_color(palette, selected))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, elided)
        painter.restore()

    def _draw_selection_stroke(
        self, painter: QPainter, palette: QPalette, pixmap_rect: QRect,
    ) -> None:
        """选中缩略图的内缘描边（修正 2：内缘绘制，修正 1 审查定稿）。

        画笔中心线落在 pixmap_rect 内缩半个笔宽的矩形上，描边最多覆盖
        ``_SELECTION_STROKE_WIDTH`` 像素的照片边缘、永不越出 image_box——
        不依赖单元格留白，也不会在任意纵横比下侵入文件名条。
        """
        inset = _SELECTION_STROKE_WIDTH // 2
        if (
            pixmap_rect.width() < 2 * _SELECTION_STROKE_WIDTH
            or pixmap_rect.height() < 2 * _SELECTION_STROKE_WIDTH
        ):
            return
        painter.setPen(
            QPen(palette.color(palette.ColorRole.Highlight), _SELECTION_STROKE_WIDTH)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(pixmap_rect.adjusted(inset, inset, -inset, -inset))

    def _draw_check_badge(
        self, painter: QPainter, palette: QPalette, pixmap_rect: QRect,
    ) -> None:
        """左上角圆形勾选章：Highlight 填充 + HighlightedText 几何折线对勾。

        对勾以三点折线绘制而非 Unicode "✓" 文本——零字体/字体回退依赖，
        Windows / Linux / CI runner 像素行为一致。颜色取活调色板。
        """
        x = pixmap_rect.left() + _CHECK_BADGE_MARGIN
        y = pixmap_rect.top() + _CHECK_BADGE_MARGIN
        size = _CHECK_BADGE_SIZE
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.color(palette.ColorRole.Highlight))
        painter.drawEllipse(QRect(x, y, size, size))
        pen = QPen(palette.color(palette.ColorRole.HighlightedText), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        unit = size / 16.0
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(x + 4.0 * unit, y + 8.5 * unit),
                    QPointF(x + 6.8 * unit, y + 11.5 * unit),
                    QPointF(x + 11.5 * unit, y + 5.0 * unit),
                ]
            )
        )

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
