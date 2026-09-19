"""Batch 4 photo-library page: three empty states, context bulk bar, detail.

Empty-state discrimination (library-empty vs filtered-empty vs busy), the
selection-count bulk bar that only appears with a selection, and the
read-only detail dialog over already-loaded data. The readiness snapshot is
doubled like in the workspace-state tests; no workers, no repository from
widgets.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox

from photo_archiver.application.dtos.workspace import (
    ModelAvailability, WorkspaceStatus,
)
from photo_archiver.domain import Photo, PhotoPath
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.main_window import MainWindow

READY = WorkspaceStatus(
    has_persons=True, has_photos=True, pending_match_count=3,
    pending_review_count=2, archivable_count=1, archive_root_available=True,
    model_availability=ModelAvailability.AVAILABLE,
)
EMPTY = replace(
    READY, has_persons=False, has_photos=False, pending_match_count=0,
    pending_review_count=0, archivable_count=0, archive_root_available=False,
)


@pytest.fixture
def library(qtbot, make_sqlite_context, monkeypatch, tmp_path):
    """A shown MainWindow over a mockable readiness snapshot; no workers."""
    context = make_sqlite_context(
        db_name="library_ui.db", model_path=tmp_path / "missing-models",
    )
    state = SimpleNamespace(value=EMPTY)
    query = Mock(side_effect=lambda root: state.value)
    monkeypatch.setattr(context.services.workspace_readiness, "execute", query)
    monkeypatch.setattr(context.worker_executor, "submit", Mock(
        side_effect=AssertionError("Library tests must not launch workers"),
    ))
    monkeypatch.setattr(context.photo_list_controller, "load_thumbnail", Mock())
    root = tmp_path / "archive"
    monkeypatch.setattr(MainWindow, "_effective_archive_root", lambda self: root)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    window._nav_list.setCurrentRow(1)  # 照片库页
    return SimpleNamespace(window=window, state=state, query=query, root=root)


def test_empty_library_shows_scan_cta(library) -> None:
    window = library.window
    library.state.value = EMPTY
    window._refresh_workspace_state()
    assert window._photo_list_stack.currentIndex() == 1
    assert window._empty_scan_button.text() == text.PHOTO_EMPTY_LIBRARY_ACTION
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()


def test_filtered_empty_shows_clear_cta_not_library_cta(library) -> None:
    """A photo-bearing library with zero results must NOT say "scan"."""
    window = library.window
    library.state.value = READY  # 库中有照片……
    window._refresh_photo_list()  # ……但真实库查询为 0（构造库为空）
    window._refresh_workspace_state()
    # has_photos=True（快照）而结果 0 → 筛选无结果态
    assert window._photo_list_stack.currentIndex() == 2
    assert window._empty_clear_button.text() == text.PHOTO_EMPTY_FILTERED_ACTION


def test_clear_filters_cta_resets_summary(library) -> None:
    window = library.window
    window._filter_bar._status_combo.setCurrentIndex(0)
    window._empty_clear_button.click()
    assert window._filter_bar._summary_label.text() == text.FILTER_SUMMARY_NONE


def test_busy_shows_progress_explanation_state(library) -> None:
    window = library.window
    reservation = window._task_coordinator.reserve("扫描")
    window._on_task_state_changed()
    assert window._photo_list_stack.currentIndex() == 3
    window._task_coordinator.release(reservation)
    window._on_task_state_changed()
    assert window._photo_list_stack.currentIndex() == 1  # 回到空库态


def test_bulk_bar_appears_only_with_selection_and_counts(library) -> None:
    window = library.window
    photo = Photo(path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg")
    window._photo_list_model.load_photos([photo])
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), selection.SelectionFlag.Select)
    assert window._bulk_archive_button.isVisible()
    assert window._bulk_archive_button.text() == text.BULK_ARCHIVE_BUTTON.format(count=1)
    assert window._bulk_delete_button.text() == text.BULK_DELETE_BUTTON.format(count=1)
    selection.clearSelection()
    assert not window._bulk_archive_button.isVisible()
    assert not window._bulk_delete_button.isVisible()


def test_bulk_bar_disables_during_busy(library) -> None:
    window = library.window
    photo = Photo(path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg")
    window._photo_list_model.load_photos([photo])
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), selection.SelectionFlag.Select)
    reservation = window._task_coordinator.reserve("扫描")
    window._render_workspace_actions()
    assert not window._bulk_archive_button.isEnabled()
    assert not window._bulk_delete_button.isEnabled()
    window._task_coordinator.release(reservation)
    window._render_workspace_actions()
    assert window._bulk_archive_button.isEnabled()
    assert window._bulk_delete_button.isEnabled()


def test_detail_dialog_opens_for_double_clicked_photo(library, monkeypatch) -> None:
    window = library.window
    photo = Photo(
        path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg",
    )
    window._photos_by_id[photo.id] = photo
    window._photo_list_model.load_photos([photo])
    index = window._photo_list_model.index(0, 0)
    exec_mock = Mock(return_value=1)
    monkeypatch.setattr(
        module, "PhotoDetailDialog",
        lambda *args, **kwargs: SimpleNamespace(exec=exec_mock),
    )
    window._on_photo_double_clicked(index)
    exec_mock.assert_called_once()


def test_detail_dialog_shows_count_after_query(library) -> None:
    """The filter-bar count reflects the query size after every refresh."""
    window = library.window
    window._refresh_photo_list()
    assert window._filter_bar._count_label.text() == text.FILTER_RESULT_COUNT.format(count=0)


def test_detail_dialog_degrades_without_data(qtbot) -> None:
    """No badge, no captured time, no thumbnail → explicit fallbacks only."""
    from PySide6.QtWidgets import QLabel

    from photo_archiver.presentation.views.photo_detail_dialog import PhotoDetailDialog

    photo = Photo(path=PhotoPath("photos/x.jpg"), folder_id=None, original_name=None)
    dialog = PhotoDetailDialog(photo, badge=None, thumbnail_path=None)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == text.PHOTO_DETAIL_TITLE
    texts = [widget.text() for widget in dialog.findChildren(QLabel)]
    assert text.PHOTO_DETAIL_CAPTURED_UNKNOWN in texts
    assert text.PHOTO_DETAIL_THUMB_PENDING in texts
    assert text.PHOTO_DETAIL_STATUS.format(badge=text.FILTER_STATUS_UNMATCHED) in texts
    assert text.PHOTO_DETAIL_PATH.format(path=str(photo.path.raw_path)) in texts