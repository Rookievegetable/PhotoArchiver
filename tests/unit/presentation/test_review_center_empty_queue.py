"""Batch2 review queue remains inspectable, with selection-aware controls."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from photo_archiver.domain import RecognitionResult
from photo_archiver.presentation.ui_text import REVIEW_EMPTY, REVIEW_STATUS_LINE
from photo_archiver.presentation.views.review_center_page import ReviewCenterPage


def test_empty_queue_stays_open_with_buttons_disabled(qtbot, monkeypatch):
    controller = Mock(list_pending=Mock(return_value=[]))
    accept = Mock()
    monkeypatch.setattr(QDialog, "accept", accept)
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)
    dialog.show()
    accept.assert_not_called()
    assert dialog.isVisible()
    assert dialog._status.text() == REVIEW_EMPTY
    assert dialog._list.isHidden()
    for button in (dialog._approve_selected, dialog._reject_selected, dialog._approve_all):
        assert not button.isEnabled()
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    controller.bulk_approve.assert_not_called()
    controller.bulk_reject.assert_not_called()


@pytest.mark.parametrize("button_name, method", [
    ("_approve_selected", "bulk_approve"),
    ("_reject_selected", "bulk_reject"),
    ("_approve_all", "bulk_approve"),
])
def test_selection_and_queue_transition_to_empty_stays_open(qtbot, button_name, method, monkeypatch):
    # Batch 5: 全部通过需要二次确认——确认路径在本测试中放行以聚焦队列语义。
    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_center_page.QMessageBox.question",
        Mock(return_value=QMessageBox.StandardButton.Yes),
    )
    result = RecognitionResult(photo_id=uuid4(), confidence=0.9, person_id=uuid4())
    pending = [result]
    controller = Mock()
    controller.list_pending.side_effect = lambda: list(pending)
    controller.resolve_row_labels.return_value = ("portrait.jpg", "Alice")
    # Stage 4 D-1: bulk_approve now takes the human-decided identity as a
    # second positional argument (None when the picker is left unresolved);
    # bulk_reject is unchanged — rejecting needs no identity.
    expected_identity = (None,) if method == "bulk_approve" else ()
    getattr(controller, method).side_effect = (
        lambda ids, person_id=None: pending.clear()
    )
    dialog = ReviewCenterPage(controller)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog._status.text() == REVIEW_STATUS_LINE.format(count=1)
    assert dialog._approve_all.isEnabled()
    assert not dialog._approve_selected.isEnabled()
    assert not dialog._reject_selected.isEnabled()
    dialog._list.item(0).setSelected(True)
    assert dialog._approve_selected.isEnabled()
    assert dialog._reject_selected.isEnabled()
    dialog._list.clearSelection()
    assert not dialog._approve_selected.isEnabled()
    assert not dialog._reject_selected.isEnabled()
    dialog._list.item(0).setSelected(True)
    qtbot.mouseClick(getattr(dialog, button_name), Qt.MouseButton.LeftButton)
    getattr(controller, method).assert_called_once_with(
        (result.id,), *expected_identity,
    )
    # 2026-10-01 页面化：页面不会"关闭"（原 dialog.accepted 语义退役），
    # 队列清空后保持可见可检视（Batch 2 语义不变）。
    assert dialog.isVisible()
    assert dialog._status.text() == REVIEW_EMPTY
    assert dialog._list.isHidden()
    assert dialog._list.count() == 0
    assert not dialog._approve_selected.isEnabled()
    assert not dialog._reject_selected.isEnabled()
    assert not dialog._approve_all.isEnabled()
