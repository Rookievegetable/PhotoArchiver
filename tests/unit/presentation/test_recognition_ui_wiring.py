"""MainWindow UI wiring tests for the Run Face Recognition action (阶段 C Commit 3).

The entry now opens the RecognitionScopeDialog and submits a traceable
recognition run through RecognitionRunController (``run_recognition`` task).
Covers the action-to-dialog-to-controller trigger, running-state action
disable, real current/total/message progress, terminal-state re-enable +
feedback (including the RecognitionRun stats summary), photo list +
review-pending refresh, dialog rejection, and refusal surfacing. The
controller's ``start_run`` is stubbed to return a controllable fake runnable
(real Qt signals) so the window wiring is exercised deterministically without
Qt threads or the AI model pack.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from unittest.mock import Mock
from uuid import uuid4

from photo_archiver.app import bootstrap_application
from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.domain import FaceCountRange
from photo_archiver.domain.entities import RecognitionRun, RecognitionRunStats
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)

TASK = "run_recognition"


def _make_runnable():
    """Build a controllable runnable with real Qt signals (smoke-test pattern)."""
    from PySide6.QtCore import QObject, Signal

    class Signals(QObject):
        started = Signal(object)
        progress = Signal(object)
        completed = Signal(object)
        failed = Signal(object)
        cancelled = Signal(object)

    class FakeRunnable:
        def __init__(self) -> None:
            self.signals = Signals()
            self.cancel_calls: list[str] = []

        def replay_pending_terminal(self) -> None:
            """Interface parity with QtWorkerRunnable (no-op: no terminal retained)."""

        def cancel(self, reason: str = "") -> None:
            """Record cooperative-cancellation requests for later assertions."""
            self.cancel_calls.append(reason)

    return FakeRunnable()


def _make_window(qtbot, tmp_path, monkeypatch) -> MainWindow:
    """Build a real MainWindow over a tmp SQLite context (smoke-test pattern)."""
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'run_ui.db'}",
        model_path=tmp_path / "missing-models",
    )
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    # Batch2 readiness: stub the workspace query to an all-ready snapshot so
    # the recognition action starts enabled — the tests below exercise the
    # entry wiring, not the (separately covered) readiness policy.
    monkeypatch.setattr(
        context.services.workspace_readiness, "execute",
        Mock(return_value=WorkspaceStatus(
            has_persons=True, has_photos=True, pending_match_count=1,
            pending_review_count=0, archivable_count=1,
            archive_root_available=True,
            model_availability=ModelAvailability.AVAILABLE,
        )),
    )
    window = MainWindow(context)
    qtbot.addWidget(window)
    return window


def _stub_scope_dialog(window, monkeypatch, *, accepted=True,
                       ranges=(FaceCountRange(1, None),), selected_only=False):
    """Double the scope dialog: auto-accept with fixed scope values."""
    from types import SimpleNamespace

    dialog = SimpleNamespace(
        exec=lambda: 1 if accepted else 0,
        selected_ranges=ranges,
        photo_scope_selected_only=selected_only,
    )
    opened: list[dict] = []
    monkeypatch.setattr(
        module, "RecognitionScopeDialog",
        lambda *args, **kwargs: (opened.append(kwargs) or dialog),
    )
    return opened


def _stub_start(window, monkeypatch):
    """Replace start_run with a recorder returning a controllable fake runnable."""
    calls: list[tuple] = []
    runnable = _make_runnable()
    monkeypatch.setattr(
        window._recognition_run_controller, "start_run",
        lambda ranges, photo_ids=None: (
            calls.append((ranges, photo_ids)) or runnable
        ),
    )
    return calls, runnable


def test_action_exists_and_enabled_by_default(qtbot, tmp_path, monkeypatch) -> None:
    """The action exists, starts enabled on a ready snapshot, and carries the count tooltip."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    assert window._match_action.text() == "运行人脸识别"
    assert window._match_action.isEnabled() is True
    assert window._workspace_controller.status.pending_match_count == 1
    assert "有 1 张照片待识别" in window._match_action.toolTip()


def test_trigger_opens_scope_dialog_and_submits_run(qtbot, tmp_path, monkeypatch) -> None:
    """Accepting the dialog submits the run with the chosen scope values."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    opened = _stub_scope_dialog(window, monkeypatch)
    calls, runnable = _stub_start(window, monkeypatch)

    window._match_action.trigger()

    assert len(opened) == 1
    assert calls == [((FaceCountRange(1, None),), None)]
    assert window._match_action.isEnabled() is False
    assert window._active_runnable is runnable
    assert window._cancel_action.isEnabled() is True


def test_trigger_with_selection_reanalyzes_selected_photos(qtbot, tmp_path, monkeypatch) -> None:
    """「重新分析选中」：范围对话框选中态透传给 start_run。"""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch, selected_only=True)
    calls, _ = _stub_start(window, monkeypatch)
    selected = (uuid4(), uuid4())
    monkeypatch.setattr(window, "_collect_selected_photo_ids", lambda: selected)

    window._match_action.trigger()

    assert calls == [((FaceCountRange(1, None),), selected)]


def test_dialog_reject_submits_nothing_and_releases_reservation(qtbot, tmp_path, monkeypatch) -> None:
    """Cancelling the scope dialog starts nothing and leaves the action usable."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch, accepted=False)
    calls, _ = _stub_start(window, monkeypatch)

    window._match_action.trigger()

    assert calls == []
    assert window._match_action.isEnabled() is True
    assert not window._task_coordinator.is_busy


def test_started_signal_keeps_action_disabled_and_updates_status(qtbot, tmp_path, monkeypatch) -> None:
    """started updates the status bar and does not unlock the action."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.started.emit(TaskStarted(TASK, "task_1"))

    assert window._match_action.isEnabled() is False
    assert "已开始" in window._status_label.text()


def test_progress_uses_real_current_total_message(qtbot, tmp_path, monkeypatch) -> None:
    """progress renders real current/total into the bar; message only into status."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.progress.emit(
        TaskProgress(TASK, "task_1", message="m", current=2, total=8)
    )
    assert window._progress.value() == 25  # 2 * 100 / 8

    runnable.signals.progress.emit(
        TaskProgress(TASK, "task_1", message="Analyzed photo x")
    )
    assert "Analyzed photo x" in window._status_label.text()
    assert "人脸识别" in window._status_label.text()
    assert window._progress.maximum() == 0


def _completed_run() -> RecognitionRun:
    """A terminal RecognitionRun with the full stats taxonomy filled in."""
    run = RecognitionRun(parameters={"photo_scope": "all"})
    run.start()
    run.complete(RecognitionRunStats(
        face_count=5, unreadable_count=2, no_face_count=1, error_count=1,
        in_scope_photo_count=3, out_of_scope_photo_count=2,
    ))
    return run


def test_completed_enables_action_refreshes_and_carries_run_stats(
    qtbot, tmp_path, monkeypatch,
) -> None:
    """completed re-enables the action, refreshes photo + review, and appends run stats."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()
    photo_refreshed: list[str] = []
    monkeypatch.setattr(window, "_refresh_photo_list", lambda: photo_refreshed.append("photos"))

    runnable.signals.completed.emit(TaskCompleted(TASK, "task_1", _completed_run()))

    assert window._match_action.isEnabled() is True
    assert window._progress.value() == 100
    assert photo_refreshed == ["photos"]
    status = window._status_label.text()
    # The run summary carries the five counters + the scope split — unreadable
    # photos can never hide inside a clean-looking "识别完成" (AUDIT 2026-09-20).
    assert "检出人脸 5 张" in status
    assert "无法读取 2 张" in status
    assert "无脸 1 张" in status
    assert "检测异常 1 张" in status
    assert "范围内 3 张 · 范围外 2 张" in status
    # The real _refresh_review_pending ran: pending count lands in the status bar.
    assert "待审核" in status


def test_completed_without_run_result_stays_clean(qtbot, tmp_path, monkeypatch) -> None:
    """无 RecognitionRun 结果的 completed 不附加识别摘要。"""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.completed.emit(TaskCompleted(TASK, "task_1"))

    status = window._status_label.text()
    assert "检出人脸" not in status and "无法读取" not in status


def test_failed_enables_action_and_surfaces_error(qtbot, tmp_path, monkeypatch) -> None:
    """failed re-enables the action, resets progress, and surfaces the error."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()
    dialogs: list[tuple[str, str]] = []
    from PySide6.QtWidgets import QMessageBox

    def _warning(parent, title: str, message: str) -> int:
        dialogs.append((title, message))
        return 0

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))

    runnable.signals.failed.emit(TaskFailed(TASK, RuntimeError("model pack missing")))

    assert window._match_action.isEnabled() is True
    assert window._progress.value() == 0
    assert "失败" in window._status_label.text()
    assert dialogs and "model pack missing" in dialogs[0][1]


def test_cancelled_enables_action_and_gives_feedback(qtbot, tmp_path, monkeypatch) -> None:
    """cancelled re-enables the action, resets progress, and reports cancellation."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.cancelled.emit(TaskCancelled(TASK, "task_1", "User requested cancel"))

    assert window._match_action.isEnabled() is True
    assert window._progress.value() == 0
    assert "已取消" in window._status_label.text()
    assert window._cancel_action.isEnabled() is False


def test_running_action_disabled_prevents_duplicate_ui_start(qtbot, tmp_path, monkeypatch) -> None:
    """While in flight the action is disabled — the UI cannot re-submit."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    calls, _ = _stub_start(window, monkeypatch)
    window._match_action.trigger()
    assert len(calls) == 1

    assert window._match_action.isEnabled() is False  # no double-click surface

    window._active_runnable.signals.completed.emit(TaskCompleted(TASK, "task_1", _completed_run()))
    assert window._match_action.isEnabled() is True


def test_refusal_surfaces_reason_and_keeps_action_enabled(qtbot, tmp_path, monkeypatch) -> None:
    """A None return from start_run surfaces last_refusal_reason, stays enabled."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(
        window._recognition_run_controller, "start_run",
        lambda ranges, photo_ids=None: (calls.append((ranges, photo_ids)) or None),
    )
    reason = "人脸识别不可用。"
    monkeypatch.setattr(window._recognition_run_controller, "last_refusal_reason", reason)

    window._match_action.trigger()

    assert len(calls) == 1
    assert window._match_action.isEnabled() is True
    assert window._status_label.text() == reason


def test_cancel_action_forwards_cancellation_to_runnable(qtbot, tmp_path, monkeypatch) -> None:
    """The shared Cancel Task action forwards a cooperative cancel to the runnable."""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    _stub_scope_dialog(window, monkeypatch)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    window._on_cancel_clicked()

    assert runnable.cancel_calls == ["User requested cancel"]
    assert window._cancel_action.isEnabled() is False
    assert "正在请求取消；当前处理单元完成后停止，已完成部分会保留" in window._status_label.text()
