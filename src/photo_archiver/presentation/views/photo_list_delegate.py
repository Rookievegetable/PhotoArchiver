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

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
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

from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.photo_list_model import STATUS_BADGE_ROLE, THUMBNAIL_ROLE

# The generation contract keeps thumbnails inside a 256px bounding box
# (PhotoListController); the DISPLAY cell shows them in a compact grid —
# the 256px source downscales on paint (SmoothTransformation).
_THUMBNAIL_BOX = 160
_TEXT_HEIGHT = 24
_PADDING = 6

# ── 参考图基线（Owner 2026-10-30）：照片墙每格＝圆角卡片 ──
# 卡片内边距（缩略图/文字与卡片边缘的距离）与两级圆角；底色/描边取活
# 调色板（Base/半透明中性灰），浅深主题下都与墙面（QSS pa-bg-window）拉开层次。
_CARD_PAD = 6
_CARD_RADIUS = 8.0
_THUMB_RADIUS = 6.0
_CARD_BORDER = QColor(127, 127, 127, 70)

# 2026-09-30 选中态三重反馈：内缘描边 + 左上角勾选章 + 文件名高亮。
# 颜色一律取自 option.palette（活调色板），禁止硬编码 RGB——本机深色主题
# 与 CI 浅色调色板不同，固定色值必然跨平台失真（Stage 14-CI 同一契约）。
_SELECTION_STROKE_WIDTH = 2
_CHECK_BADGE_SIZE = 16
_CHECK_BADGE_MARGIN = 4

# ── G-4 状态角标 → 参考图基线：缩略图右上角内嵌彩色胶囊 ──
# 胶囊直接画在照片之上，颜色必须跨主题、跨照片底色保持可读，故用固定
# 实底 + 白字（对比度均 ≥4.5:1，实算见行内）；未匹配沿用原半透明黑签。
_BADGE_PILL_DANGER = (QColor("#c62828"), QColor("#ffffff"))  # 已拒绝（5.62:1）
_BADGE_PILL_SUCCESS = (QColor("#107c10"), QColor("#ffffff"))  # 已通过（5.37:1）
_BADGE_PILL_WARNING = (QColor("#b45309"), QColor("#ffffff"))  # 待审核（4.63:1）
_BADGE_PILL_INFO = (QColor("#1f4e79"), QColor("#ffffff"))  # 已归档（8.16:1）
_BADGE_PILL_NEUTRAL = (QColor(0, 0, 0, 150), QColor("#ffffff"))  # 未匹配
_BADGE_PILL_MARGIN = 4


def pill_colors(badge_text: str) -> tuple[QColor, QColor]:
    """Map a badge text (may be composite, e.g.「已通过 · 已归档」) to pill colors.

    判定序＝拒绝（最需警惕）→ 通过 → 待审核 → 已归档（复合串的后缀态）；
    其余（含未匹配）＝中性黑签。文本来自 ui_text 冻结键，零硬编码中文。
    """
    if text.STATUS_BADGE_REJECTED in badge_text:
        return _BADGE_PILL_DANGER
    if text.STATUS_BADGE_APPROVED in badge_text:
        return _BADGE_PILL_SUCCESS
    if text.STATUS_BADGE_PENDING in badge_text:
        return _BADGE_PILL_WARNING
    if text.STATUS_BADGE_ARCHIVED in badge_text:
        return _BADGE_PILL_INFO
    return _BADGE_PILL_NEUTRAL

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
        # 参考图基线：先画每格圆角卡片底（Base 填充 + 中性描边），缩略图与
        # 文字都内缩 _CARD_PAD，形成「照片卡片」而非裸缩略图。
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        card_rect = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(_CARD_BORDER, 1))
        painter.setBrush(option.palette.color(QPalette.ColorRole.Base))  # type: ignore[attr-defined]
        painter.drawRoundedRect(card_rect, _CARD_RADIUS, _CARD_RADIUS)

        image_box = QRect(
            rect.left() + _CARD_PAD,
            rect.top() + _CARD_PAD,
            max(1, rect.width() - 2 * _CARD_PAD),
            min(
                _THUMBNAIL_BOX,
                max(1, rect.height() - _TEXT_HEIGHT - 2 * _CARD_PAD),
            ),
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
        # 圆角缩略图：按缩略图矩形裁剪（参考图卡片内圆角照片）。
        thumb_path = QPainterPath()
        thumb_path.addRoundedRect(
            QRectF(pixmap_rect), _THUMB_RADIUS, _THUMB_RADIUS,
        )
        painter.setClipPath(thumb_path)
        painter.drawPixmap(pixmap_rect, scaled)
        painter.setClipping(False)

        # 选中态：内缘描边 + 左上角勾选章（仅 State_Selected，绘制顺序在
        # 缩略图之上、状态胶囊与文件名之前——后者各自重设画笔/画刷）。
        # 勾选章前关抗锯齿：几何折线必须像素级锐利（选中态像素探针契约）。
        palette = option.palette  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
        selected = bool(option.state & QStyle.StateFlag.State_Selected)  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
        if selected:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_selection_stroke(painter, palette, pixmap_rect)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            self._draw_check_badge(painter, palette, pixmap_rect)

        # G-4：状态角标——参考图基线：彩色胶囊内嵌在缩略图右上角（贴实际
        # 照片矩形，竖图/横图都不再悬浮错位）；颜色按识别/归档状态取语义色。
        badge = index.data(STATUS_BADGE_ROLE)
        if badge:
            badge_text = str(badge)
            metrics = QFontMetrics(option.font)  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
            chip_width = metrics.horizontalAdvance(badge_text) + 2 * _PADDING
            chip_height = metrics.height() + 2
            chip = QRect(
                pixmap_rect.right() - chip_width - _BADGE_PILL_MARGIN,
                pixmap_rect.top() + _BADGE_PILL_MARGIN,
                chip_width,
                chip_height,
            )
            pill_bg, pill_fg = pill_colors(badge_text)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(pill_bg)
            radius = chip_height / 2.0
            painter.drawRoundedRect(QRectF(chip), radius, radius)
            painter.setPen(pill_fg)
            painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, badge_text)

        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        text_rect = QRect(
            rect.left() + _CARD_PAD,
            image_box.bottom() + 2,
            rect.width() - 2 * _CARD_PAD,
            _TEXT_HEIGHT,
        )
        elided = QFontMetrics(option.font).elidedText(  # type: ignore[attr-defined]  # PySide6 6.8.3 stubs
            str(name), Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(name_color(palette, selected))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, elided)
        painter.restore()

    def _draw_selection_stroke(
        self, painter: QPainter, palette: QPalette, pixmap_rect: QRect,
    ) -> None:
        """选中缩略图的内缘描边（修正 2：内缘绘制，修正 1 审查定稿）。

        参考图基线：描边走圆角路径，与圆角缩略图同心内缩——画笔中心线落在
        pixmap_rect 内缩 1px 的圆角矩形上，描边最多覆盖 2 像素的照片边缘、
        永不越出缩略图（圆角处也不外溢到卡片底上），不依赖单元格留白。
        """
        inset = _SELECTION_STROKE_WIDTH // 2
        if (
            pixmap_rect.width() < 2 * _SELECTION_STROKE_WIDTH
            or pixmap_rect.height() < 2 * _SELECTION_STROKE_WIDTH
        ):
            return
        stroke_path = QPainterPath()
        inner = QRectF(pixmap_rect).adjusted(inset, inset, -inset, -inset)
        stroke_path.addRoundedRect(
            inner, max(1.0, _THUMB_RADIUS - inset), max(1.0, _THUMB_RADIUS - inset),
        )
        painter.setPen(
            QPen(palette.color(palette.ColorRole.Highlight), _SELECTION_STROKE_WIDTH)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(stroke_path)

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
