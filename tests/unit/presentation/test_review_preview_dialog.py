"""Review preview dialog tests (2026-10-01 功能完善：HD 审片闭环).

The preview subclasses PhotoDetailDialog (all HD machinery inherited);
these tests drive the review layer only with an injected fake decoder:
navigation (snapshot cursor + replace_photo rebind), single-result
approve/reject with the page-provided identity (D1-A/D2-A), the stay-on-
place behavior after acting (D3-B), no-identity confirmation, bounds and
keyboard navigation (D4-A).
"""

from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QMessageBox

from photo_archiver.domain import Photo, PhotoPath, RecognitionResult
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.review_preview_dialog import (
    ReviewPreviewDialog,
)


def _entry():
    return RecognitionResult(photo_id=uuid4(), confidence=0.9, person_id=uuid4())


def _photo(name: str) -> Photo:
    return Photo(path=PhotoPath(f"photos/{name}"), folder_id=None, original_name=name)


def _solid_qimage(width: int, height: int, rgb: tuple[int, int, int]) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(*rgb))
    return image


def _fake_decoder():
    """Record requested paths; return a deterministic QImage per call."""
    calls: list[object] = []

    def decoder(path, box, dpr):  # noqa: ANN001
        calls.append(path)
        return _solid_qimage(300, 200, (10, 200, 30))

    decoder.calls = calls  # type: ignore[attr-defined]
    return decoder


def _make_dialog(qtbot, entries, index, *, identity=None, identity_text="未指定"):
    """Build the preview over real Photo entities + fake decoder + Mock callbacks."""
    photos = {entry.id: _photo(f"{entry.photo_id}.jpg") for entry in entries}
    photo_for = lambda result: photos.get(result.id)  # noqa: E731
    on_approve = Mock()
    on_reject = Mock()
    dialog = ReviewPreviewDialog(
        entries, index, photo_for=photo_for,
        identity=identity, identity_text=identity_text,
        on_approve=on_approve, on_reject=on_reject,
        decoder=_fake_decoder(),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog, on_approve, on_reject


def test_t1_initial_state_shows_cursor_and_decodes_opened_row(qtbot) -> None:
    entries = [_entry() for _ in range(3)]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 1)
    assert dialog._position_label.text() == text.REVIEW_PREVIEW_POSITION.format(index=2, total=3)
    assert dialog._prev_button.isEnabled()
    assert dialog._next_button.isEnabled()
    assert dialog._identity_label.text() == text.REVIEW_PREVIEW_IDENTITY_PREFIX + "未指定"
    # worker 拾取是异步的——waitUntil 等待（不 sleep、不做即时竞态断言）
    qtbot.waitUntil(lambda: len(dialog._decoder.calls) == 1, timeout=5000)


def test_t2_navigation_moves_cursor_and_restarts_decode(qtbot) -> None:
    entries = [_entry() for _ in range(3)]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 0)
    decoder = dialog._decoder
    name_before = dialog._name_label.text()
    dialog._on_next()
    assert dialog._position_label.text() == text.REVIEW_PREVIEW_POSITION.format(index=2, total=3)
    # worker 拾取是异步的——waitUntil 等待（不 sleep、不做即时竞态断言）
    qtbot.waitUntil(lambda: len(decoder.calls) == 2, timeout=5000)
    assert dialog._name_label.text() != name_before  # 元数据已重绑到下一张


def test_t3_bounds_disable_navigation_buttons(qtbot) -> None:
    entries = [_entry() for _ in range(2)]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 0)
    assert not dialog._prev_button.isEnabled()  # 首条禁用上一张
    assert dialog._next_button.isEnabled()
    dialog._on_next()
    assert not dialog._next_button.isEnabled()  # 末条禁用下一张
    assert dialog._prev_button.isEnabled()


def test_t4_approve_single_result_stays_in_place(qtbot) -> None:
    entries = [_entry() for _ in range(2)]
    identity = uuid4()
    dialog, on_approve, on_reject = _make_dialog(
        qtbot, entries, 0, identity=identity, identity_text="Alice",
    )
    assert dialog._identity_label.text() == text.REVIEW_PREVIEW_IDENTITY_PREFIX + "Alice"
    dialog._approve_button.click()
    on_approve.assert_called_once_with(entries[0], identity)
    # D3-B：停留原地——游标不动、按钮转已处理态防重复提交
    assert dialog._position_label.text() == text.REVIEW_PREVIEW_POSITION.format(index=1, total=2)
    assert not dialog._approve_button.isEnabled()
    assert not dialog._reject_button.isEnabled()
    assert dialog._acted_hint.text() == text.REVIEW_PREVIEW_DONE_APPROVED
    assert dialog._acted_hint.isVisible()


def test_t5_approve_without_identity_asks_first(qtbot, monkeypatch) -> None:
    entries = [_entry()]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 0, identity=None)
    question = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_preview_dialog.QMessageBox.question",
        question,
    )
    dialog._approve_button.click()
    on_approve.assert_not_called()  # 默认 No 不通过
    question.return_value = QMessageBox.StandardButton.Yes
    dialog._approve_button.click()
    on_approve.assert_called_once_with(entries[0], None)


def test_t6_reject_marks_row_and_calls_callback(qtbot) -> None:
    entries = [_entry() for _ in range(2)]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 1)
    dialog._reject_button.click()
    on_reject.assert_called_once_with(entries[1])
    assert dialog._acted_hint.text() == text.REVIEW_PREVIEW_DONE_REJECTED
    assert not dialog._approve_button.isEnabled()
    on_approve.assert_not_called()


def test_t7_keyboard_arrows_navigate(qtbot) -> None:
    entries = [_entry() for _ in range(3)]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 1)
    qtbot.keyClick(dialog, Qt.Key.Key_Right)
    assert dialog._position_label.text() == text.REVIEW_PREVIEW_POSITION.format(index=3, total=3)
    qtbot.keyClick(dialog, Qt.Key.Key_Left)
    qtbot.keyClick(dialog, Qt.Key.Key_Left)
    assert dialog._position_label.text() == text.REVIEW_PREVIEW_POSITION.format(index=1, total=3)


def test_t8_replace_photo_rebinds_metadata_labels(qtbot) -> None:
    entries = [_entry() for _ in range(2)]
    dialog, on_approve, on_reject = _make_dialog(qtbot, entries, 0)
    name_before = dialog._name_label.text()
    dialog._on_next()
    assert dialog._name_label.text() != name_before
    assert dialog._name_label.text() == text.PHOTO_DETAIL_NAME.format(
        name=dialog._photo.original_name,
    )
