"""MainWindow UI wiring tests for the Run Face Recognition action (Commit 3).

Covers the action-to-controller trigger, running-state action disable, real
current/total/message progress, terminal-state re-enable + feedback, photo
list + review-pending refresh, and refusal surfacing. The match controller's
``start_match`` is stubbed to return a controllable fake runnable (real Qt
signals) so the window wiring is exercised deterministically without Qt
threads or the AI model pack.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from photo_archiver.app import bootstrap_application  # noqa: F401
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)


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


def _make_window(qtbot, tmp_path) -> MainWindow:
    """Build a real MainWindow over a tmp SQLite context (smoke-test pattern)."""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'match_ui.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    return window


def _stub_start(window, monkeypatch):
    """Replace start_match with a recorder returning a controllable fake runnable."""
    calls: list[str] = []
    runnable = _make_runnable()
    monkeypatch.setattr(
        window._match_controller,
        "start_match",
        lambda: (calls.append("start") or runnable),
    )
    return calls, runnable


def test_action_exists_and_enabled_by_default(qtbot, tmp_path) -> None:
    """The Run Face Recognition toolbar action exists and starts enabled."""
    window = _make_window(qtbot, tmp_path)
    assert window._match_action.text() == "运行人脸识别"
    assert window._match_action.isEnabled() is True


def test_trigger_calls_start_match_and_disables_action(qtbot, tmp_path, monkeypatch) -> None:
    """Clicking the action submits via the controller and locks the action."""
    window = _make_window(qtbot, tmp_path)
    calls, runnable = _stub_start(window, monkeypatch)

    window._match_action.trigger()

    assert calls == ["start"]
    assert window._match_action.isEnabled() is False
    assert window._active_runnable is runnable
    assert window._cancel_action.isEnabled() is True


def test_started_signal_keeps_action_disabled_and_updates_status(qtbot, tmp_path, monkeypatch) -> None:
    """started updates the status bar and does not unlock the action."""
    window = _make_window(qtbot, tmp_path)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.started.emit(TaskStarted("match_persons", "task_1"))

    assert window._match_action.isEnabled() is False
    assert "已开始" in window._status_label.text()


def test_progress_uses_real_current_total_message(qtbot, tmp_path, monkeypatch) -> None:
    """progress renders real current/total into the bar; message only into status."""
    window = _make_window(qtbot, tmp_path)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.progress.emit(
        TaskProgress("match_persons", "task_1", message="m", current=2, total=8)
    )
    assert window._progress.value() == 25  # 2 * 100 / 8

    runnable.signals.progress.emit(
        TaskProgress("match_persons", "task_1", message="Matching batch 2")
    )
    assert window._status_label.text() == "Matching batch 2"


def test_completed_enables_action_and_refreshes_photo_and_review(qtbot, tmp_path, monkeypatch) -> None:
    """completed re-enables the action and triggers photo + review-pending refresh."""
    window = _make_window(qtbot, tmp_path)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()
    photo_refreshed: list[str] = []
    monkeypatch.setattr(window, "_refresh_photo_list", lambda: photo_refreshed.append("photos"))

    runnable.signals.completed.emit(TaskCompleted("match_persons", "task_1"))

    assert window._match_action.isEnabled() is True
    assert window._progress.value() == 100
    assert photo_refreshed == ["photos"]
    # The real _refresh_review_pending ran: re-queried list_pending and wrote
    # the pending count into the status bar (0 in an empty test DB).
    assert "待审核" in window._status_label.text()


def test_failed_enables_action_and_surfaces_error(qtbot, tmp_path, monkeypatch) -> None:
    """failed re-enables the action, resets progress, and surfaces the error."""
    window = _make_window(qtbot, tmp_path)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()
    dialogs: list[tuple[str, str]] = []
    from PySide6.QtWidgets import QMessageBox

    def _warning(parent, title: str, message: str) -> int:
        dialogs.append((title, message))
        return 0

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))

    runnable.signals.failed.emit(TaskFailed("match_persons", RuntimeError("model pack missing")))

    assert window._match_action.isEnabled() is True
    assert window._progress.value() == 0
    assert "失败" in window._status_label.text()
    assert dialogs and "model pack missing" in dialogs[0][1]


def test_cancelled_enables_action_and_gives_feedback(qtbot, tmp_path, monkeypatch) -> None:
    """cancelled re-enables the action, resets progress, and reports cancellation."""
    window = _make_window(qtbot, tmp_path)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    runnable.signals.cancelled.emit(TaskCancelled("match_persons", "task_1", "User requested cancel"))

    assert window._match_action.isEnabled() is True
    assert window._progress.value() == 0
    assert "已取消" in window._status_label.text()
    assert window._cancel_action.isEnabled() is False


def test_running_action_disabled_prevents_duplicate_ui_start(qtbot, tmp_path, monkeypatch) -> None:
    """While in flight the action is disabled — the UI cannot re-submit (AC-014)."""
    window = _make_window(qtbot, tmp_path)
    calls, _ = _stub_start(window, monkeypatch)
    window._match_action.trigger()
    assert calls == ["start"]

    assert window._match_action.isEnabled() is False  # no double-click surface

    runnable_signals_completed = window._active_runnable.signals
    runnable_signals_completed.completed.emit(TaskCompleted("match_persons", "task_1"))
    assert window._match_action.isEnabled() is True


def test_refusal_surfaces_reason_and_keeps_action_enabled(qtbot, tmp_path, monkeypatch) -> None:
    """A None return from start_match surfaces last_refusal_reason, stays enabled."""
    window = _make_window(qtbot, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        window._match_controller,
        "start_match",
        lambda: (calls.append("start") or None),
    )
    reason = "No persons imported. Import people first."
    monkeypatch.setattr(window._match_controller, "last_refusal_reason", reason)

    window._match_action.trigger()

    assert calls == ["start"]
    assert window._match_action.isEnabled() is True
    assert window._status_label.text() == reason


def test_cancel_action_forwards_cancellation_to_runnable(qtbot, tmp_path, monkeypatch) -> None:
    """The shared Cancel Task action forwards a cooperative cancel to the runnable."""
    window = _make_window(qtbot, tmp_path)
    _, runnable = _stub_start(window, monkeypatch)
    window._match_action.trigger()

    window._on_cancel_clicked()

    assert runnable.cancel_calls == ["User requested cancel"]
    assert window._cancel_action.isEnabled() is False
    assert "正在取消" in window._status_label.text()

