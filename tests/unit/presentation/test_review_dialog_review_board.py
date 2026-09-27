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
from PySide6.QtWidgets import QMessageBox

from photo_archiver.domain import Photo, PhotoPath, RecognitionResult
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.review_dialog import (
    ReviewDialog,
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
    dialog = ReviewDialog(controller)
    qtbot.addWidget(dialog)

    row = dialog._list.item(0).text()
    assert "照片=portrait.jpg" in row
    assert "人员=Alice" in row
    assert "置信度：较高（0.87）" in row  # band + exact value for audit
    assert "状态：待审核" in row


def test_queue_header_with_total_sits_above_the_list(qtbot) -> None:
    controller = _controller([_result(0.9), _result(0.5)])
    dialog = ReviewDialog(controller)
    qtbot.addWidget(dialog)

    assert dialog._status.text() == text.REVIEW_STATUS_LINE.format(count=2)
    # Header is the top-most layout item, above the list (Batch 5 requirement).
    layout = dialog.layout()
    assert layout.itemAt(0).widget() is dialog._status
    assert layout.indexOf(dialog._list) > layout.indexOf(dialog._status)


# ── Counted action buttons ───────────────────────────────────────────────────


def test_buttons_carry_exact_selected_count(qtbot) -> None:
    pending = [_result(0.9), _result(0.8), _result(0.7)]
    dialog = ReviewDialog(_controller(pending))
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
    dialog = ReviewDialog(_controller([_result(0.9), _result(0.8)]))
    qtbot.addWidget(dialog)
    assert dialog._approve_all.text() == text.REVIEW_APPROVE_ALL_COUNTED.format(count=2)


# ── 全部通过 double confirmation ─────────────────────────────────────────────


def test_approve_all_without_confirmation_changes_nothing(qtbot, monkeypatch) -> None:
    """Answering the confirmation with No must not touch the queue."""
    pending = [_result(0.9), _result(0.8)]
    controller = _controller(pending)
    question = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(
        "photo_archiver.presentation.views.review_dialog.QMessageBox.question", question,
    )
    dialog = ReviewDialog(controller)
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
        "photo_archiver.presentation.views.review_dialog.QMessageBox.question",
        Mock(return_value=QMessageBox.StandardButton.Yes),
    )
    dialog = ReviewDialog(controller)
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

    dialog = ReviewDialog(controller, thumbnail_source=source)  # type: ignore[arg-type]
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
    dialog = ReviewDialog(controller, thumbnail_source=source)  # type: ignore[arg-type]
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
    dialog = ReviewDialog(controller, thumbnail_source=source)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)

    source.thumbnail_loaded.emit(photo.id, None)
    assert dialog._list.item(0).icon().isNull()


def test_missing_photo_entity_degrades_without_thumbnail_request(qtbot) -> None:
    controller = _controller([_result(0.9)])
    controller.photo_for.return_value = None
    source = _FakeThumbnailSource()

    ReviewDialog(controller, thumbnail_source=source)  # type: ignore[arg-type]

    source.load_thumbnail.assert_not_called()
