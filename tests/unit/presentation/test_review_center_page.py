"""Batch 5 review board: readable rows, counted buttons, confirmed bulk.

The dialog must let a reviewer decide with context — photo/person names, a
textual confidence band that keeps the exact value for audit, an explicit
status — and the one blind-batch hazard ("全部通过") must be confirmable with
the exact count and an honest no-undo statement. Thumbnails ride the existing
async loader (injected), never disk IO in the widget.
"""

from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from photo_archiver.domain import Photo, PhotoPath, RecognitionResult
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.review_center_page import (
    ReviewCenterPage,
    confidence_band,
)


def _result(confidence: float) -> RecognitionResult:
    return RecognitionResult(photo_id=uuid4(), confidence=confidence, person_id=uuid4())


def _controller(pending: list[RecognitionResult]) -> Mock:
    controller = Mock()
    controller.list_pending.side_effect = lambda: list(pending)
    controller.resolve_row_labels.return_value = ("portrait.jpg", "Alice")
    return controller


# ── Confidence wording (exact value stays on the row for audit) ──────────────


@pytest.mark.parametrize("value, band", [
    (0.95, text.REVIEW_CONFIDENCE_VERY_HIGH),
    (0.90, text.REVIEW_CONFIDENCE_VERY_HIGH),
    (0.80, text.REVIEW_CONFIDENCE_HIGH),
    (0.65, text.REVIEW_CONFIDENCE_MEDIUM),
    (0.10, text.REVIEW_CONFIDENCE_LOW),
])
def test_confidence_band_wording(value, band) -> None:
    assert confidence_band(value) == band


def test_row_shows_names_band_with_exact_value_and_status(qtbot) -> None:
    """A row reads as a sentence, not a bare decimal; the value stays visible."""
    controller = _controller([_result(0.87)])
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)

    row = dialog._list.item(0).text()
    assert "照片=portrait.jpg" in row
    assert "人员=Alice" in row
    assert "置信度：较高（0.87）" in row  # band + exact value for audit
    assert "状态：待审核" in row


def test_queue_header_with_total_sits_above_the_list(qtbot) -> None:
    controller = _controller([_result(0.9), _result(0.5)])
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)

    assert dialog._status.text() == text.REVIEW_STATUS_LINE.format(count=2)
    # Header sits above the list (Batch 5 requirement); 2026-10-01 页面化后
    # 顶部先有引导条行（guidance layout），状态行紧随其后。
    layout = dialog.layout()
    assert layout.itemAt(0).widget() is None  # itemAt(0) = 引导条 layout
    assert layout.itemAt(0).layout().indexOf(dialog._pairing_button) >= 0
    assert layout.itemAt(1).widget() is dialog._status
    assert layout.indexOf(dialog._list) > layout.indexOf(dialog._status)


# ── Counted action buttons ───────────────────────────────────────────────────


def test_buttons_carry_exact_selected_count(qtbot) -> None:
    pending = [_result(0.9), _result(0.8), _result(0.7)]
    dialog = ReviewCenterPage(_controller(pending))
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog._approve_selected.text() == text.REVIEW_APPROVE_SELECTED
    dialog._list.item(0).setSelected(True)
    dialog._list.item(2).setSelected(True)
    assert dialog._approve_selected.text() == text.REVIEW_APPROVE_SELECTED_COUNTED.format(count=2)
    assert dialog._reject_selected.text() == text.REVIEW_REJECT_SELECTED_COUNTED.format(count=2)
    dialog._list.clearSelection()
    assert dialog._approve_selected.text() == text.REVIEW_APPROVE_SELECTED


def test_approve_all_button_states_the_queue_size(qtbot) -> None:
    dialog = ReviewCenterPage(_controller([_result(0.9), _result(0.8)]))
    qtbot.addWidget(dialog)
    assert dialog._approve_all.text() == text.REVIEW_APPROVE_ALL_COUNTED.format(count=2)


# ── 全部通过 double confirmation ─────────────────────────────────────────────


def test_approve_all_without_confirmation_changes_nothing(qtbot, monkeypatch) -> None:
    """Answering the confirmation with No must not touch the queue."""
    pending = [_result(0.9), _result(0.8)]
    controller = _controller(pending)
    question = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_center_page.QMessageBox.question", question,
    )
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._approve_all.click()
    question.assert_called_once()
    confirm_text = question.call_args[0][2]
    assert "2" in confirm_text  # exact count in the confirmation
    controller.bulk_approve.assert_not_called()
    assert dialog._list.count() == 2


def test_approve_all_confirmed_batch_approves_everything(qtbot, monkeypatch) -> None:
    pending = [_result(0.9), _result(0.8), _result(0.7)]
    controller = _controller(pending)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_center_page.QMessageBox.question",
        Mock(return_value=QMessageBox.StandardButton.Yes),
    )
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)
    dialog.show()

    expected_ids = tuple(r.id for r in pending)
    # Stage 4 D-1: the second positional arg is the human-decided identity
    # (None here — the picker is left unresolved and the warning confirmed).
    controller.bulk_approve.side_effect = lambda ids, person_id=None: pending.clear()
    dialog._approve_all.click()
    controller.bulk_approve.assert_called_once_with(expected_ids, None)
    assert dialog._list.count() == 0  # queue refreshed after the batch


# ── Thumbnails ride the shared async loader ─────────────────────────────────


class _FakeThumbnailSource(QObject):
    """PhotoListController shape: async load request + arrival signal."""

    thumbnail_loaded = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        self.load_thumbnail = Mock()


def test_rows_request_thumbnails_via_injected_loader(qtbot) -> None:
    photo = Photo(path=PhotoPath("photos/p.jpg"), folder_id=None, original_name="p.jpg")
    result = RecognitionResult(photo_id=photo.id, confidence=0.9, person_id=uuid4())
    controller = _controller([result])
    controller.photo_for.return_value = photo
    source = _FakeThumbnailSource()

    dialog = ReviewCenterPage(controller, thumbnail_source=source)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)

    source.load_thumbnail.assert_called_once_with(photo.id, photo.path.raw_path)


def test_arriving_thumbnail_attaches_to_all_rows_of_that_photo(qtbot, tmp_path) -> None:
    photo = Photo(path=PhotoPath("photos/p.jpg"), folder_id=None, original_name="p.jpg")
    results = [
        RecognitionResult(photo_id=photo.id, confidence=0.9, person_id=uuid4()),
        RecognitionResult(photo_id=photo.id, confidence=0.6, person_id=uuid4()),
    ]
    controller = _controller(results)
    controller.photo_for.return_value = photo
    source = _FakeThumbnailSource()
    dialog = ReviewCenterPage(controller, thumbnail_source=source)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)

    pixmap_image = tmp_path / "thumb.png"
    from PySide6.QtGui import QPixmap

    QPixmap(8, 8).save(str(pixmap_image))
    source.thumbnail_loaded.emit(photo.id, pixmap_image)

    from PySide6.QtGui import QIcon

    for row in range(dialog._list.count()):
        icon = dialog._list.item(row).icon()
        assert isinstance(icon, QIcon) and not icon.isNull()


def test_thumbnail_miss_leaves_rows_without_icon(qtbot) -> None:
    """A None arrival (generation failed) degrades silently — row stays text-only."""
    photo = Photo(path=PhotoPath("photos/p.jpg"), folder_id=None, original_name="p.jpg")
    result = RecognitionResult(photo_id=photo.id, confidence=0.9, person_id=uuid4())
    controller = _controller([result])
    controller.photo_for.return_value = photo
    source = _FakeThumbnailSource()
    dialog = ReviewCenterPage(controller, thumbnail_source=source)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)

    source.thumbnail_loaded.emit(photo.id, None)
    assert dialog._list.item(0).icon().isNull()


def test_missing_photo_entity_degrades_without_thumbnail_request(qtbot) -> None:
    controller = _controller([_result(0.9)])
    controller.photo_for.return_value = None
    source = _FakeThumbnailSource()

    ReviewCenterPage(controller, thumbnail_source=source)  # type: ignore[arg-type]

    source.load_thumbnail.assert_not_called()


def test_double_click_opens_review_preview_with_snapshot(qtbot, monkeypatch) -> None:
    """双击行 → 打开审核预览：队列快照 = 展示行、游标定位双击行、身份传递。"""
    results = [_result(0.9), _result(0.8)]
    controller = _controller(results)
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)

    opened: dict[str, object] = {}

    class _FakePreview(QWidget):
        identity_changed = Signal(object)

        def __init__(self, entries, index, **kwargs):
            super().__init__()
            opened["entries"] = list(entries)
            opened["index"] = index
            opened["kwargs"] = kwargs

        def exec(self):
            opened["exec"] = True
            return 1

    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_center_page.ReviewPreviewDialog",
        _FakePreview,
    )
    dialog._list.itemDoubleClicked.emit(dialog._list.item(1))
    assert opened["exec"] is True
    assert opened["entries"] == results  # 队列快照与展示行一致
    assert opened["index"] == 1  # 游标定位双击行
    kwargs = opened["kwargs"]
    assert kwargs["identity"] is None  # 页面选择器未指定 → 预览下拉初始未指定
    assert kwargs["persons"] == []  # 控制器无人员读侧时的降级空列表
    assert callable(kwargs["on_approve"]) and callable(kwargs["on_reject"])


def test_double_click_passes_persons_and_selected_identity(qtbot, monkeypatch) -> None:
    """页面选择器已选人员 + 人员列表 → 预览下拉初始定位并可改选回写。"""
    person_id = uuid4()
    result = _result(0.9)
    controller = _controller([result])
    controller.list_persons = Mock(return_value=[(person_id, "Alice")])
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)

    opened: dict[str, object] = {}

    class _FakePreview(QWidget):
        identity_changed = Signal(object)

        def __init__(self, entries, index, **kwargs):
            super().__init__()
            opened["kwargs"] = kwargs

        def exec(self):
            return 1

    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_center_page.ReviewPreviewDialog",
        _FakePreview,
    )
    dialog._identity_combo.setCurrentIndex(1)  # Alice
    dialog._list.itemDoubleClicked.emit(dialog._list.item(0))
    kwargs = opened["kwargs"]
    assert kwargs["identity"] is person_id  # 初始值 = 页面选择器当前值
    assert kwargs["persons"] == [(person_id, "Alice")]
    # 回写链路：预览内改选身份 → 页面选择器同步（连续双击身份保持连续）
    page_combo = dialog._identity_combo
    slot = dialog._apply_preview_identity
    slot(person_id)
    assert page_combo.currentData() == person_id


def test_double_click_preview_callbacks_drive_controller_and_wall_refresh(
    qtbot,
) -> None:
    """预览回调 → bulk 路径 + 队列刷新 + review_changed（照片墙即时刷新）。"""
    result = _result(0.9)
    controller = _controller([result])
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)
    changed = Mock()
    dialog.review_changed.connect(changed)

    dialog._apply_preview_approve(result, None)
    controller.bulk_approve.assert_called_once_with((result.id,), None)
    changed.assert_called()
    controller.bulk_reject.reset_mock()
    changed.reset_mock()
    dialog._apply_preview_reject(result)
    controller.bulk_reject.assert_called_once_with((result.id,))
    changed.assert_called()


def test_double_click_missing_photo_entity_is_silent(qtbot) -> None:
    controller = _controller([_result(0.9)])
    controller.photo_for.return_value = None
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)
    # 实体缺失（已删除等）：静默忽略，不弹预览不崩溃。
    dialog._list.itemDoubleClicked.emit(dialog._list.item(0))


def test_identity_combo_is_searchable_and_marked(qtbot) -> None:
    """审核页身份下拉：可编辑搜索 + 展开按钮放大标记（Owner 功能完善）。"""
    dialog = ReviewCenterPage(_controller([_result(0.9)]))
    qtbot.addWidget(dialog)
    combo = dialog._identity_combo
    assert combo.isEditable()
    assert combo.completer() is not None
    assert combo.property("searchableCombo") == "true"
