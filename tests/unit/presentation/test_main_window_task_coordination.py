"""Batch1 cross-task and synchronous-entry guards through the actual window."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from photo_archiver.app import bootstrap_application
from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.dtos.import_draft import ImportDraft
from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.domain import MatchStatus, PhotoSearchCriteria
from photo_archiver.domain.entities import ImportBatch, ImportDraftRow
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.ui_text import STATUS_CANCELLING, TASK_LABELS
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.import_preview_dialog import CONFIRM_SYNC_LIMIT
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskFailed, TaskProgress
from photo_archiver.workers.qt_executor import QtWorkerSignals


READY = WorkspaceStatus(
    has_persons=True, has_photos=True, pending_match_count=1,
    pending_review_count=0, archivable_count=1, archive_root_available=True,
    model_availability=ModelAvailability.AVAILABLE,
)


def _assert_persistent_actions_enabled(window) -> None:
    """The ready snapshot enables workflows, but deletion still needs selection."""
    assert not window._delete_photos_action.isEnabled()
    for action in window._conflicting_actions:
        if action is not window._delete_photos_action:
            assert action.isEnabled(), action.toolTip()


class Runnable:
    def __init__(self, pending=None):
        self.signals = QtWorkerSignals()
        self.pending = pending
        self.cancel_calls = []

    def cancel(self, reason=""):
        self.cancel_calls.append(reason)

    def replay_pending_terminal(self):
        event, self.pending = self.pending, None
        if isinstance(event, TaskCompleted):
            self.signals.completed.emit(event)
        elif isinstance(event, TaskCancelled):
            self.signals.cancelled.emit(event)
        elif isinstance(event, TaskFailed):
            self.signals.failed.emit(event)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'tasks.db'}",
        model_path=tmp_path / "missing-models",
    )
    context = bootstrap_application(settings)
    monkeypatch.setattr(context.services.workspace_readiness, "execute", Mock(return_value=READY))
    window = MainWindow(context)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    return window


def _stage_a_parse_and_dialog_doubles(window, monkeypatch):
    """Stage A two-stage doubles for the import entry.

    The parse service is faked to a persisted-looking draft with
    ``CONFIRM_SYNC_LIMIT + 1`` rows, so the window's confirm takes the Worker
    path (submission via ``worker_executor.submit``) — the point these tests
    stub. The preview dialog auto-accepts (same modal doubling policy as the
    export/archive dialogs above).
    """
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("people.txt", ""))
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


def prepare(window, monkeypatch, tmp_path, name, runnable):
    """Use real controller wiring, stub only submission/preparation."""
    dialog = SimpleNamespace(
        exec=lambda: 1, output_path=tmp_path / "out.csv", scope=ExportScope.ALL,
        format_name="csv", conflict_strategy="skip", dry_run=False,
    )
    if name == "import_people":
        # Stage A: parse/dialog doubled; confirm (>CONFIRM_SYNC_LIMIT rows)
        # submits ConfirmImportTask through the shared worker executor.
        _stage_a_parse_and_dialog_doubles(window, monkeypatch)
        controller, method, entry = window._context.worker_executor, "submit", "import"
    elif name == "scan_and_register_photos":
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
        controller, method, entry = window._scan_controller, "scan_folder", "scan"
    elif name == "run_recognition":
        # 阶段 C Commit 3: the entry opens the scope dialog, then submits via
        # RecognitionRunController.start_run — both are doubled here.
        monkeypatch.setattr(module, "RecognitionScopeDialog", lambda *a, **k: SimpleNamespace(
            exec=lambda: 1, selected_ranges=(), photo_scope_selected_only=False,
        ))
        controller, method, entry = window._recognition_run_controller, "start_run", "match"
    elif name == "archive_photos":
        monkeypatch.setattr(window, "_effective_archive_root", lambda: tmp_path)
        monkeypatch.setattr(window._archive_controller, "preview",
                            lambda *a, **k: SimpleNamespace(planned_count=1))
        monkeypatch.setattr(module, "ArchivePreviewDialog", lambda *a, **k: dialog)
        controller, method, entry = window._archive_controller, "execute", "archive"
    else:
        monkeypatch.setattr(module, "ExportDialog", lambda *a, **k: dialog)
        controller, method, entry = window._export_controller, "export", "export"
    submit = Mock(return_value=runnable)
    monkeypatch.setattr(controller, method, submit)
    return getattr(window, f"_on_{entry}_clicked"), submit


# face_clustering：阶段 D 只落数据与 Worker，无窗口入口（方案 D-4 UI 后续提交）。
_WINDOW_TASK_NAMES = [
    n for n in TASK_LABELS
    if n not in ("import_confirm", "match_persons", "face_clustering")
]


@pytest.mark.parametrize("name", _WINDOW_TASK_NAMES)
def test_five_tasks_block_every_conflicting_entry_and_cancel_correctly(
    window, monkeypatch, tmp_path, name,
):
    runnable = Runnable()
    entry, submit = prepare(window, monkeypatch, tmp_path, name, runnable)
    original = [(a.isEnabled(), a.toolTip()) for a in window._conflicting_actions]
    entry()
    assert submit.call_count == 1
    for action in window._conflicting_actions:
        assert not action.isEnabled()
        assert TASK_LABELS[name] in action.toolTip()
    for other in ("import", "scan", "match", "archive", "export", "review", "settings",
                  "detect_duplicates", "delete_photos", "delete_person"):
        getattr(window, f"_on_{other}_clicked")()  # bypass disabled QAction
    window._on_plugin_action("anything")
    assert submit.call_count == 1
    window._on_cancel_clicked()
    window._on_cancel_clicked()
    assert runnable.cancel_calls == ["User requested cancel"]
    assert window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    runnable.signals.progress.emit(TaskProgress(name, current=2, total=8, message="working"))
    assert "25%" in window._status_label.text()
    assert "working" in window._status_label.text()
    assert STATUS_CANCELLING in window._status_label.text()
    runnable.signals.progress.emit(TaskProgress(name, current=3, total=0, message="unknown"))
    assert window._progress.maximum() == 0
    assert "%" not in window._status_label.text()
    assert STATUS_CANCELLING in window._status_label.text()
    runnable.signals.cancelled.emit(TaskCancelled(name))
    assert not window._task_coordinator.is_busy
    assert [(a.isEnabled(), a.toolTip()) for a in window._conflicting_actions] == original


@pytest.mark.parametrize("name", _WINDOW_TASK_NAMES)
@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_all_early_terminals_release_and_refresh_once(window, monkeypatch, tmp_path, name, kind):
    event = {"completed": TaskCompleted(name), "failed": TaskFailed(name, ValueError("bad")),
             "cancelled": TaskCancelled(name)}[kind]
    runnable = Runnable(event)
    entry, _ = prepare(window, monkeypatch, tmp_path, name, runnable)
    refresh = Mock()
    monkeypatch.setattr(window, "_refresh_photo_list", refresh)
    entry()
    getattr(runnable.signals, kind).emit(event)
    assert refresh.call_count == 1
    assert not window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    _assert_persistent_actions_enabled(window)


def test_double_import_during_picker_and_submission_is_reserved(window, monkeypatch, tmp_path):
    runnable = Runnable()
    entry, submit = prepare(window, monkeypatch, tmp_path, "import_people", runnable)

    def picker(*args):
        loop = QEventLoop()
        QTimer.singleShot(0, lambda: (entry(), window._on_export_clicked(), loop.quit()))
        loop.exec()
        assert not window._cancel_action.isEnabled()
        return "people.txt", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", picker)

    def submission(*args):
        entry()
        window._on_match_clicked()
        return runnable

    submit.side_effect = submission
    entry()
    entry()
    assert submit.call_count == 1


@pytest.mark.parametrize("path", ["review", "settings", "detect_duplicates", "delete_photos",
                                  "delete_person", "plugin"])
def test_sync_modal_path_blocks_reentrant_task(window, monkeypatch, path):
    start = Mock()
    # 阶段 C：识别入口先开范围对话框；忙态下 @_exclusive 在对话框之前拦截，
    # 因此这里只桩提交入口验证「忙时不重入」。
    monkeypatch.setattr(window._recognition_run_controller, "start_run", start)

    def nested(*args, **kwargs):
        loop = QEventLoop()
        QTimer.singleShot(0, lambda: (window._on_match_clicked(), loop.quit()))
        loop.exec()
        assert window._task_coordinator.is_busy
        return 0

    dialog = SimpleNamespace(exec=nested)
    if path == "review":
        monkeypatch.setattr(module, "ReviewDialog", lambda *a: dialog)
    elif path == "settings":
        monkeypatch.setattr(module, "SettingsDialog", lambda *a: dialog)
    elif path == "delete_person":
        monkeypatch.setattr(module, "PersonDeletionDialog", lambda *a, **k: dialog)
    elif path == "delete_photos":
        monkeypatch.setattr(window, "_collect_selected_photo_ids", lambda: ())
        monkeypatch.setattr(QMessageBox, "information", nested)
    elif path == "detect_duplicates":
        monkeypatch.setattr(window._context.detect_duplicates_controller, "detect_and_show", nested)
    else:
        plugin = SimpleNamespace(actions=lambda: [SimpleNamespace(id="test")],
                                 execute_action=nested)
        monkeypatch.setattr(window._plugin_registry, "_enabled", {"test": plugin}, raising=False)
        # Registry's public enabled_plugins property is the host dispatch surface.
        monkeypatch.setattr(type(window._plugin_registry), "enabled_plugins",
                            property(lambda self: {"test": plugin}))
    if path == "plugin":
        window._on_plugin_action("test")
    else:
        getattr(window, f"_on_{path}_clicked")()
    start.assert_not_called()
    assert not window._task_coordinator.is_busy


def test_failed_retry_stale_events_and_previous_action_state(window, monkeypatch, tmp_path):
    old = Runnable()
    entry, submit = prepare(window, monkeypatch, tmp_path, "import_people", old)
    action = window._export_action
    action.setEnabled(False)
    action.setToolTip("previous reason")
    entry()
    old.signals.failed.emit(TaskFailed("import_people", ValueError("bad")))
    assert not action.isEnabled()
    assert action.toolTip() == "previous reason"
    fresh = Runnable()
    submit.return_value = fresh
    entry()
    status = window._status_label.text()
    old.signals.completed.emit(TaskCompleted("import_people"))
    old.signals.progress.emit(TaskProgress("import_people", message="stale"))
    assert window._active_runnable is fresh
    assert window._status_label.text() == status
    window._on_cancel_clicked()
    assert not old.cancel_calls
    assert fresh.cancel_calls == ["User requested cancel"]


@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_terminal_refresh_keeps_latest_criteria_and_partial_results(
    window, monkeypatch, tmp_path, kind,
):
    runnable = Runnable()
    entry, _ = prepare(window, monkeypatch, tmp_path, "import_people", runnable)
    entry()
    criteria = PhotoSearchCriteria(match_status=MatchStatus.PENDING)
    window._on_filter_changed(criteria)
    search = Mock(return_value=[])
    all_photos = Mock(return_value=[])
    catalog = Mock(return_value=[])
    monkeypatch.setattr(window._photo_list_controller, "search_photos", search)
    monkeypatch.setattr(window._photo_list_controller, "list_photos", all_photos)
    monkeypatch.setattr(window._context.services.list_persons, "execute", catalog)
    event = {"completed": TaskCompleted("import_people"),
             "failed": TaskFailed("import_people", ValueError("partial")),
             "cancelled": TaskCancelled("import_people")}[kind]
    getattr(runnable.signals, kind).emit(event)
    search.assert_called_once_with(criteria)
    all_photos.assert_not_called()
    catalog.assert_called_once()
    assert window._current_criteria is criteria


def test_cancel_exception_restores_retry_without_false_cancellation(window, monkeypatch, tmp_path):
    runnable = Runnable()
    entry, _ = prepare(window, monkeypatch, tmp_path, "import_people", runnable)
    entry()
    monkeypatch.setattr(runnable, "cancel", Mock(side_effect=RuntimeError("cancel failed")))
    window._on_cancel_clicked()
    assert window._active_runnable is runnable
    assert window._cancel_action.isEnabled()
    assert STATUS_CANCELLING not in window._status_label.text()
    assert "取消请求未能发送" in window._status_label.text()
    assert all(not a.isEnabled() for a in window._conflicting_actions)
    monkeypatch.setattr(runnable, "cancel", lambda reason: runnable.cancel_calls.append(reason))
    window._on_cancel_clicked()
    assert runnable.cancel_calls == ["User requested cancel"]
    assert STATUS_CANCELLING in window._status_label.text()
    runnable.signals.cancelled.emit(TaskCancelled("import_people"))
    assert not window._task_coordinator.is_busy


@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_refresh_exception_releases_actions_and_preserves_failure_dialog(
    window, monkeypatch, tmp_path, kind,
):
    runnable = Runnable()
    entry, _ = prepare(window, monkeypatch, tmp_path, "import_people", runnable)
    entry()
    monkeypatch.setattr(window, "_refresh_photo_list", Mock(side_effect=OSError("database unavailable")))
    event = {"completed": TaskCompleted("import_people"),
             "failed": TaskFailed("import_people", RuntimeError("original worker error")),
             "cancelled": TaskCancelled("import_people")}[kind]
    getattr(runnable.signals, kind).emit(event)
    assert not window._task_coordinator.is_busy
    _assert_persistent_actions_enabled(window)
    assert "页面刷新失败" in window._status_label.text()
    if kind == "failed":
        assert QMessageBox.warning.call_args.args[2] == "original worker error"


def test_submission_exception_releases_reservation(window, monkeypatch, tmp_path):
    entry, submit = prepare(window, monkeypatch, tmp_path, "import_people", Runnable())
    submit.side_effect = OSError("unavailable")
    entry()
    assert not window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    _assert_persistent_actions_enabled(window)
