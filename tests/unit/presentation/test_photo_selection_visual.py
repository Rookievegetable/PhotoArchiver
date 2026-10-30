"""Photo wall selection-state rendering probes (2026-09-30 选中态优化).

Direct delegate paint onto QImage — no view, no pipeline: the delegate reads
a stub index and the probe asserts painted pixels. Selected cells must carry
(a) an inner-edge stroke in the **live palette** Highlight around the actual
scaled-pixmap rect and (b) a top-left geometric checkmark badge (Highlight
fill + HighlightedText polyline check — zero font dependency); unselected
cells must not. All color assertions compare against the palette object
handed to the delegate with a deliberately non-default Highlight — never
fixed RGB (Stage 14-CI contract: local dark+purple palette vs CI light+blue).

Geometry notes (production-accurate, 参考图基线 2026-10-30 卡片化后): cell =
delegate sizeHint 172×190; card pad 6 → thumbnail box = 160×min(160,
190-24-12)=154; a 400×300 source scales to 160×120 centered → y offset 23.
Badge = 16px circle at pixmap top-left + 4px margin; status pill anchored to
the pixmap top-right (G-4 → 参考图基线).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPalette
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

from PIL import Image

from photo_archiver.presentation.views.photo_list_delegate import (
    _BADGE_PILL_MARGIN,
    _CARD_PAD,
    _CHECK_BADGE_MARGIN,
    _CHECK_BADGE_SIZE,
    _TEXT_HEIGHT,
    _THUMBNAIL_BOX,
    PhotoThumbnailDelegate,
    name_color,
    pill_colors,
)
from photo_archiver.presentation.views.photo_list_model import (
    STATUS_BADGE_ROLE,
    THUMBNAIL_ROLE,
)

_CELL = QRect(0, 0, 172, 190)
_SOURCE_COLOR = (196, 42, 88)
# 刻意区别于任何平台默认调色板的主题中立色——断言只认 option.palette。
_HIGHLIGHT = QColor(24, 98, 51)
_HIGHLIGHTED_TEXT = QColor(250, 250, 210)

# 400×300 源图 KeepAspectRatio 装进 160×154 缩略框 → 160×120 居中。
_SCALED_W, _SCALED_H = 160, 120


class _StubIndex:
    """Minimal index stand-in: the delegate reads only ``data(role)``."""

    def __init__(self, thumbnail: object, name: str = "LEI00572.JPG",
                 badge: object = None) -> None:
        self._thumbnail = thumbnail
        self._name = name
        self._badge = badge

    def data(self, role: int) -> object:
        if role == THUMBNAIL_ROLE:
            return self._thumbnail
        if role == Qt.ItemDataRole.DisplayRole:
            return self._name
        if role == STATUS_BADGE_ROLE:
            return self._badge
        return None


def _write_source_image(tmp_path: Path) -> Path:
    """Solid-color lossless PNG → every painted thumbnail pixel is exact."""
    source = tmp_path / "sample.png"
    Image.new("RGB", (400, 300), _SOURCE_COLOR).save(source)
    return source


@pytest.fixture(autouse=True)
def _qt_app(qapp):
    """Direct QPainter probes require a live QApplication (no qtbot here)."""


def _pixmap_rect() -> QRect:
    """The scaled-pixmap rect exactly as the delegate computes it."""
    box_left = _CELL.left() + _CARD_PAD
    box_top = _CELL.top() + _CARD_PAD
    box_width = _CELL.width() - 2 * _CARD_PAD
    box_height = min(
        _THUMBNAIL_BOX,
        max(1, _CELL.height() - _TEXT_HEIGHT - 2 * _CARD_PAD),
    )
    return QRect(
        box_left + (box_width - _SCALED_W) // 2,
        box_top + (box_height - _SCALED_H) // 2,
        _SCALED_W,
        _SCALED_H,
    )


def _pill_rect(badge_text: str, option: QStyleOptionViewItem) -> QRect:
    """The status-pill rect exactly as the delegate computes it."""
    metrics = QFontMetrics(option.font)
    chip_width = metrics.horizontalAdvance(badge_text) + 2 * 6  # _PADDING
    chip_height = metrics.height() + 2
    rect = _pixmap_rect()
    return QRect(
        rect.right() - chip_width - _BADGE_PILL_MARGIN,
        rect.top() + _BADGE_PILL_MARGIN,
        chip_width,
        chip_height,
    )


def _badge_top_left() -> QPoint:
    rect = _pixmap_rect()
    return QPoint(rect.left() + _CHECK_BADGE_MARGIN, rect.top() + _CHECK_BADGE_MARGIN)


def _make_option(selected: bool, hovered: bool = False) -> QStyleOptionViewItem:
    option = QStyleOptionViewItem()
    option.rect = QRect(_CELL)
    option.state = QStyle.StateFlag.State_Enabled
    if selected:
        option.state |= QStyle.StateFlag.State_Selected
    if hovered:
        option.state |= QStyle.StateFlag.State_MouseOver
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Highlight, _HIGHLIGHT)
    palette.setColor(QPalette.ColorRole.HighlightedText, _HIGHLIGHTED_TEXT)
    option.palette = palette
    return option


def _paint(option: QStyleOptionViewItem, thumbnail: object, badge: object = None) -> QImage:
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        PhotoThumbnailDelegate().paint(painter, option, _StubIndex(thumbnail, badge=badge))
    finally:
        painter.end()
    return image


class _NoThumbnailModel(QAbstractListModel):
    """One row with no THUMBNAIL_ROLE — drives the real fallback paint path.

    ``super().paint()`` needs a genuine QModelIndex (PySide6 converts the
    third argument), so the fallback probe cannot use the stub index.
    """

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if role == Qt.ItemDataRole.DisplayRole:
            return "missing-thumb.jpg"
        return None


def test_unselected_cell_has_no_selection_visuals(tmp_path: Path) -> None:
    source = _write_source_image(tmp_path)
    image = _paint(_make_option(selected=False), source)
    rect = _pixmap_rect()
    # 内缘描边应在的位置必须仍是照片本色；左上角没有任何 Highlight 色块。
    assert image.pixelColor(rect.left() + 1, rect.center().y()) == QColor(*_SOURCE_COLOR)
    assert image.pixelColor(rect.right() - 1, rect.center().y()) == QColor(*_SOURCE_COLOR)
    badge = _badge_top_left()
    for x in range(badge.x(), badge.x() + _CHECK_BADGE_SIZE):
        for y in range(badge.y(), badge.y() + _CHECK_BADGE_SIZE):
            assert image.pixelColor(x, y) != _HIGHLIGHT


def test_selected_cell_draws_inner_stroke_and_badge(tmp_path: Path) -> None:
    source = _write_source_image(tmp_path)
    option = _make_option(selected=True)
    image = _paint(option, source)
    highlight = option.palette.color(QPalette.ColorRole.Highlight)
    highlighted_text = option.palette.color(QPalette.ColorRole.HighlightedText)
    rect = _pixmap_rect()
    # 内缘描边：色值 == 交给委托的活调色板 Highlight（非固定 RGB）。
    assert image.pixelColor(rect.left() + 1, rect.center().y()) == highlight
    assert image.pixelColor(rect.right() - 1, rect.center().y()) == highlight
    assert image.pixelColor(rect.top() + rect.width() // 2, rect.top() + 1) == highlight
    # 照片本体不被整体覆盖（描边只吃边缘 ≤2px）。
    assert image.pixelColor(rect.center()) == QColor(*_SOURCE_COLOR)
    # 勾选章：Highlight 圆片填充 + HighlightedText 几何折线（零字体依赖）。
    badge = _badge_top_left()
    assert image.pixelColor(badge.x() + 3, badge.y() + 3) == highlight
    assert image.pixelColor(badge.x() + 9, badge.y() + 8) == highlighted_text


def test_selection_visuals_survive_hover_combinations(tmp_path: Path) -> None:
    """§22：Selected+Hovered 不丢失描边/章，Unselected+Hovered 不误画。"""
    source = _write_source_image(tmp_path)
    rect = _pixmap_rect()
    badge = _badge_top_left()

    selected_hovered = _paint(_make_option(selected=True, hovered=True), source)
    assert selected_hovered.pixelColor(rect.left() + 1, rect.center().y()) == _HIGHLIGHT
    assert selected_hovered.pixelColor(badge.x() + 3, badge.y() + 3) == _HIGHLIGHT

    unselected_hovered = _paint(_make_option(selected=False, hovered=True), source)
    assert unselected_hovered.pixelColor(
        rect.left() + 1, rect.center().y()
    ) == QColor(*_SOURCE_COLOR)
    assert unselected_hovered.pixelColor(badge.x() + 3, badge.y() + 3) != _HIGHLIGHT


def test_selected_missing_thumbnail_falls_back_without_crash() -> None:
    """§14 文档化降级：无缩略图 + 选中 → 平台 fallback 路径，不崩溃。"""
    option = _make_option(selected=True)
    model = _NoThumbnailModel()
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        PhotoThumbnailDelegate().paint(painter, option, model.index(0, 0))
    finally:
        painter.end()
    assert not image.isNull()


def test_name_color_follows_palette() -> None:
    """§16 文件名选中色契约（纯函数钉死，规避文本渲染的平台差异）。"""
    palette = QPalette()
    assert name_color(palette, True) == palette.color(
        QPalette.ColorRole.HighlightedText
    )
    assert name_color(palette, False) == palette.color(QPalette.ColorRole.Text)


# ── G-4 → 参考图基线（Owner 2026-10-30）：状态角标＝缩略图右上角语义胶囊 ──


def test_pill_colors_map_semantics_by_text() -> None:
    """复合串按语义判定：拒绝>通过>待审核>已归档，其余中性。"""
    assert pill_colors("已拒绝")[0] == QColor("#c62828")
    assert pill_colors("已通过 · 已归档")[0] == QColor("#107c10")
    assert pill_colors("待审核")[0] == QColor("#b45309")
    assert pill_colors("已归档")[0] == QColor("#1f4e79")
    neutral_bg, neutral_fg = pill_colors("未匹配")
    assert neutral_fg == QColor("#ffffff")
    assert neutral_bg.alpha() == 150  # 原黑签语义（半透明中性）


def test_status_badge_paints_pill_inside_pixmap(tmp_path: Path) -> None:
    """状态胶囊贴在实际缩略图右上角（竖图/横图都不再悬浮错位）。"""
    source = _write_source_image(tmp_path)
    option = _make_option(selected=False)
    image = _paint(option, source, badge="待审核")
    chip = _pill_rect("待审核", option)
    bg, fg = pill_colors("待审核")
    # 胶囊底色（取样避开居中文本的字形）＝语义 warning 橙。
    assert image.pixelColor(chip.left() + 1, chip.center().y()) == bg
    # 胶囊必须完全落在缩略图矩形内（对齐参考图「内嵌」语义）。
    pixmap = _pixmap_rect()
    assert pixmap.contains(chip)
    # 未选中态：勾选章区域依旧无 Highlight（选中视觉只属于选中态）。
    badge = _badge_top_left()
    assert image.pixelColor(badge.x() + 3, badge.y() + 3) != _HIGHLIGHT


def test_status_pill_colors_differ_by_status(tmp_path: Path) -> None:
    """已通过（绿）与已拒绝（红）在照片上画出不同的语义底色。"""
    source = _write_source_image(tmp_path)
    option = _make_option(selected=False)
    approved = _paint(option, source, badge="已通过")
    rejected = _paint(option, source, badge="已拒绝")
    approved_chip = _pill_rect("已通过", option)
    rejected_chip = _pill_rect("已拒绝", option)
    assert (
        approved.pixelColor(approved_chip.left() + 1, approved_chip.center().y())
        == pill_colors("已通过")[0]
    )
    assert (
        rejected.pixelColor(rejected_chip.left() + 1, rejected_chip.center().y())
        == pill_colors("已拒绝")[0]
    )
