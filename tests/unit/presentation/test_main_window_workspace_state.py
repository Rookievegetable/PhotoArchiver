"""Batch2 readiness rendering and next-step routing without workers or model IO."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton

from photo_archiver.application.dtos.import_draft import ImportDraft
from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.domain import Photo, PhotoPath
from photo_archiver.domain.entities import ImportBatch, ImportDraftRow
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.import_preview_dialog import CONFIRM_SYNC_LIMIT
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskFailed
from photo_archiver.workers.qt_executor import QtWorkerSignals


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
def workspace(qtbot, make_sqlite_context, monkeypatch, tmp_path):
    context = make_sqlite_context(
        db_name="workspace_ui.db", model_path=tmp_path / "missing-models",
    )
    state = SimpleNamespace(value=EMPTY)
    query = Mock(side_effect=lambda root: state.value)
    monkeypatch.setattr(context.services.workspace_readiness, "execute", query)
    monkeypatch.setattr(context.worker_executor, "submit", Mock(
        side_effect=AssertionError("Workspace UI tests must not launch workers"),
    ))
    monkeypatch.setattr(context.photo_list_controller, "load_thumbnail", Mock())
    root = tmp_path / "archive"
    monkeypatch.setattr(MainWindow, "_effective_archive_root", lambda self: root)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    return SimpleNamespace(window=window, state=state, query=query, root=root)


def test_initial_snapshot_queries_effective_root_and_explains_empty_actions(workspace):
    window = workspace.window
    workspace.query.assert_called_once_with(workspace.root)
    assert not window._match_action.isEnabled()
    assert window._match_action.toolTip() == text.REFUSAL_NO_PERSONS
    assert not window._archive_action.isEnabled()
    assert window._archive_action.toolTip() == text.WORKSPACE_ROOT_UNAVAILABLE
    assert window._review_action.isEnabled()
    assert window._review_action.toolTip() == text.REVIEW_EMPTY
    assert not window._delete_photos_action.isEnabled()
    assert window._delete_photos_action.toolTip() == text.DELETE_PHOTOS_NO_SELECTION
    window._nav_list.setCurrentRow(1)  # 照片库页：next 引导按钮的宿主页（Batch 3 IA）
    for button, action in ((window._match_next_button, "import"),
                           (window._archive_next_button, "settings")):
        assert isinstance(button, QPushButton)
        assert button.isVisible()
        assert button.isEnabled()
        assert button.property("next_action") == action
    assert not window._cancel_action.isEnabled()


@pytest.mark.parametrize("status, match_tooltip, next_action", [
    (replace(READY, has_photos=False, pending_match_count=0), text.REFUSAL_NO_PHOTOS, "scan"),
    (replace(READY, pending_match_count=0), text.WORKSPACE_ALL_MATCHED, "review"),
    (replace(READY, model_availability=ModelAvailability.MISSING), text.WORKSPACE_MODEL_MISSING, "model"),
    (replace(READY, model_availability=ModelAvailability.UNKNOWN), text.WORKSPACE_MODEL_UNKNOWN, "model"),
])
def test_refresh_replaces_tooltips_and_next_step_then_hides_ready_buttons(
    workspace, status, match_tooltip, next_action,
):
    window = workspace.window
    window._nav_list.setCurrentRow(1)  # next 引导按钮的宿主页（Batch 3 IA）
    workspace.state.value = replace(status, archivable_count=0)
    window._refresh_workspace_state()
    assert not window._match_action.isEnabled()
    assert window._match_action.toolTip() == match_tooltip
    assert window._match_next_button.isVisible()
    assert window._match_next_button.property("next_action") == next_action
    assert not window._archive_action.isEnabled()
    assert window._archive_action.toolTip() == text.WORKSPACE_ARCHIVE_EMPTY
    assert window._archive_next_button.isVisible()
    assert window._archive_next_button.property("next_action") == "review"
    workspace.state.value = READY
    window._refresh_workspace_state()
    assert window._match_action.isEnabled()
    assert window._match_action.toolTip() == text.WORKSPACE_MATCH_READY.format(count=3)
    assert window._archive_action.isEnabled()
    assert window._archive_action.toolTip() == text.WORKSPACE_ARCHIVE_READY.format(count=1)
    assert window._review_action.toolTip() == text.STATUS_PENDING_REVIEW_COUNT.format(count=2)
    assert not window._match_next_button.isVisible()
    assert not window._archive_next_button.isVisible()


def test_selection_clear_and_model_reset_only_render_cached_snapshot(workspace):
    window = workspace.window
    workspace.state.value = READY
    window._refresh_workspace_state()
    photo = Photo(path=PhotoPath("photos/a.jpg"), folder_id=None, original_name="a.jpg")
    window._photo_list_model.load_photos([photo])
    workspace.query.reset_mock()
    workspace.state.value = EMPTY  # Must not leak into rendering without refresh.
    selection = window._photo_list.selectionModel()
    selection.select(window._photo_list_model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    assert window._delete_photos_action.isEnabled()
    selection.clearSelection()
    assert not window._delete_photos_action.isEnabled()
    selection.select(window._photo_list_model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    assert window._delete_photos_action.isEnabled()
    window._photo_list_model.load_photos([])
    assert not window._delete_photos_action.isEnabled()
    assert window._delete_photos_action.toolTip() == text.DELETE_PHOTOS_NO_SELECTION
    assert window._match_action.isEnabled()
    assert window._archive_action.isEnabled()
    workspace.query.assert_not_called()


def test_cancel_tooltip_transitions_preserve_one_shot_request(workspace, monkeypatch):
    window = workspace.window
    assert window._cancel_action.toolTip() == text.WORKSPACE_CANCEL_IDLE
    runnable = Runnable()
    _stage_a_import_doubles(window, monkeypatch, runnable)
    window._on_import_clicked()
    assert window._cancel_action.isEnabled()
    assert window._cancel_action.toolTip() == text.WORKSPACE_CANCEL_READY
    window._cancel_action.trigger()
    assert not window._cancel_action.isEnabled()
    assert window._cancel_action.toolTip() == text.STATUS_CANCELLING
    window._on_cancel_clicked()
    runnable.cancel.assert_called_once_with("User requested cancel")
    assert window._task_coordinator.is_busy
    runnable.signals.cancelled.emit(TaskCancelled("import_people"))
    assert not window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    assert window._cancel_action.toolTip() == text.WORKSPACE_CANCEL_IDLE


def test_refresh_while_reserved_keeps_actions_locked_then_uses_cached_latest(workspace):
    window = workspace.window
    reservation = window._task_coordinator.reserve("preparing")
    workspace.state.value = READY
    window._refresh_workspace_state()
    assert all(not action.isEnabled() for action in window._conflicting_actions)
    assert not window._match_next_button.isEnabled()
    assert not window._archive_next_button.isEnabled()
    workspace.query.reset_mock()
    window._task_coordinator.release(reservation)
    workspace.query.assert_not_called()
    assert window._match_action.isEnabled()
    assert window._archive_action.isEnabled()
    assert window._review_action.isEnabled()
    assert not window._delete_photos_action.isEnabled()
    assert not window._match_next_button.isVisible()
    assert not window._archive_next_button.isVisible()


class Runnable:
    def __init__(self):
        self.signals = QtWorkerSignals()
        self.cancel = Mock()

    def replay_pending_terminal(self):
        pass


def _stage_a_import_doubles(window, monkeypatch, runnable) -> None:
    """Stage A two-stage doubles for the import entry.

    The parse service is faked to a draft with ``CONFIRM_SYNC_LIMIT + 1`` rows
    so the confirm submits through ``worker_executor.submit`` (which this
    helper re-stubs to return the test runnable, overriding the fixture's
    no-worker guard for this specific flow); the preview dialog auto-accepts.
    """
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("people.txt", ""))
    batch = ImportBatch(file_name="people.txt", file_hash="stub", source_type="txt")
    rows = [
        ImportDraftRow(batch_id=batch.id, source_row=index, parsed_name=f"人员{index}")
        for index in range(1, CONFIRM_SYNC_LIMIT + 2)
    ]
    draft = ImportDraft(batch=batch, rows=rows, header=None, field_mapping={"name": 0})
    monkeypatch.setattr(
        window._context.services.parse_import_draft, "execute", lambda command: draft,
    )
    monkeypatch.setattr(
        module, "ImportPreviewDialog",
        lambda *a, **k: SimpleNamespace(
            exec=lambda: 1, batch_id=batch.id, row_count=len(rows),
        ),
    )
    monkeypatch.setattr(
        window._context.worker_executor, "submit", Mock(return_value=runnable),
    )


@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
@pytest.mark.parametrize("initial, latest", [(EMPTY, READY), (READY, EMPTY)])
def test_terminal_refresh_restores_latest_not_pre_task_action_state(
    workspace, monkeypatch, kind, initial, latest,
):
    window = workspace.window
    window._nav_list.setCurrentRow(1)  # next 引导按钮的宿主页（Batch 3 IA）
    workspace.state.value = initial
    window._refresh_workspace_state()
    runnable = Runnable()
    _stage_a_import_doubles(window, monkeypatch, runnable)
    window._on_import_clicked()
    assert window._task_coordinator.is_busy
    assert all(not action.isEnabled() for action in window._conflicting_actions)
    assert not window._match_next_button.isEnabled()
    assert not window._archive_next_button.isEnabled()
    assert window._cancel_action.isEnabled()
    workspace.state.value = latest
    workspace.query.reset_mock()
    event = {"completed": TaskCompleted("import_people"),
             "failed": TaskFailed("import_people", RuntimeError("partial batch")),
             "cancelled": TaskCancelled("import_people")}[kind]
    getattr(runnable.signals, kind).emit(event)
    workspace.query.assert_called_once_with(workspace.root)
    assert not window._task_coordinator.is_busy
    assert window._match_action.isEnabled() == (latest is READY)
    assert window._archive_action.isEnabled() == (latest is READY)
    assert window._review_action.isEnabled()
    assert not window._delete_photos_action.isEnabled()
    assert not window._cancel_action.isEnabled()
    if latest is EMPTY:
        assert window._match_action.toolTip() == text.REFUSAL_NO_PERSONS
        assert window._archive_action.toolTip() == text.WORKSPACE_ROOT_UNAVAILABLE
        assert window._match_next_button.isVisible() and window._match_next_button.isEnabled()
        assert window._archive_next_button.isVisible() and window._archive_next_button.isEnabled()


@pytest.mark.parametrize("route", ["import", "scan"])
def test_next_button_routes_to_existing_picker(workspace, monkeypatch, qtbot, route):
    window = workspace.window
    workspace.state.value = EMPTY if route == "import" else replace(READY, has_photos=False)
    window._refresh_workspace_state()
    picker = Mock(return_value=("", "") if route == "import" else "")
    monkeypatch.setattr(QFileDialog, "getOpenFileName" if route == "import" else "getExistingDirectory", picker)
    qtbot.mouseClick(window._match_next_button, Qt.MouseButton.LeftButton)
    picker.assert_called_once()
    assert not window._task_coordinator.is_busy


@pytest.mark.parametrize("route, button_name", [
    ("settings", "_archive_next_button"),
    ("review", "_archive_next_button"),
    ("review", "_match_next_button"),
])
def test_next_button_invokes_decorated_dialog_handler_after_idle_and_refreshes(
    workspace, monkeypatch, qtbot, route, button_name,
):
    window = workspace.window
    workspace.state.value = EMPTY if route == "settings" else replace(READY, archivable_count=0, pending_match_count=0)
    window._refresh_workspace_state()
    button = getattr(window, button_name)
    assert button.property("next_action") == route
    calls = []

    def execute():
        # Exercise the real decorated handler, not a replacement that bypasses admission.
        assert window._task_coordinator.is_busy
        calls.append(route)
        workspace.state.value = READY
        return 1

    monkeypatch.setattr(module, "SettingsDialog" if route == "settings" else "ReviewDialog",
                        lambda *args, **kwargs: SimpleNamespace(exec=execute))
    reservation = window._task_coordinator.reserve("busy")
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert calls == []
    window._task_coordinator.release(reservation)
    assert button.isEnabled()
    workspace.query.reset_mock()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert calls == [route]
    assert not window._task_coordinator.is_busy
    workspace.query.assert_called_once_with(workspace.root)
    assert window._match_action.isEnabled()
    assert window._archive_action.isEnabled()


def test_model_next_button_shows_help_without_starting_recognition(workspace, monkeypatch, qtbot):
    window = workspace.window
    workspace.state.value = replace(READY, model_availability=ModelAvailability.MISSING)
    window._refresh_workspace_state()
    start = Mock()
    monkeypatch.setattr(window._match_controller, "start_match", start)
    qtbot.mouseClick(window._match_next_button, Qt.MouseButton.LeftButton)
    QMessageBox.information.assert_called_once_with(
        window, text.WORKSPACE_MODEL_HELP_TITLE, text.WORKSPACE_MODEL_HELP,
    )
    window._on_match_clicked()  # Disabled QAction must not be the only model gate.
    start.assert_not_called()
    assert not window._task_coordinator.is_busy
