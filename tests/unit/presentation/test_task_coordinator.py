"""Batch1 admission, identity, replay and main-thread routing contracts."""

from threading import Thread
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QThread

from photo_archiver.presentation.controllers.import_people_controller import ImportPeopleController
from photo_archiver.presentation.task_coordinator import TaskCoordinator
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskFailed, TaskProgress
from photo_archiver.workers.qt_executor import QtWorkerSignals


class Runnable:
    """Controllable real signals, optionally replaying a terminal at connection."""

    def __init__(self, terminal=None, task_id=""):
        self.signals = QtWorkerSignals()
        self.task = SimpleNamespace(task_id=task_id)
        self.pending = terminal
        self.cancel_calls = []

    def cancel(self, reason=""):
        self.cancel_calls.append(reason)

    def replay_pending_terminal(self):
        if self.pending is not None:
            event, self.pending = self.pending, None
            self.emit(event)

    def emit(self, event):
        channel = {
            TaskCompleted: "completed", TaskFailed: "failed", TaskCancelled: "cancelled",
            TaskProgress: "progress",
        }[type(event)]
        getattr(self.signals, channel).emit(event)


def bind(coordinator, runnable):
    reservation = coordinator.reserve("测试任务")
    assert reservation is not None
    coordinator.bind(runnable, ImportPeopleController.connect_signals)
    return reservation


@pytest.mark.parametrize("event", [TaskCompleted("import_people"),
    TaskCancelled("import_people"), TaskFailed("import_people", ValueError("bad"))])
def test_early_terminal_replay_releases_once(qtbot, event):
    coordinator = TaskCoordinator()
    terminal = []
    coordinator.terminal.connect(terminal.append)
    runnable = Runnable(event)
    bind(coordinator, runnable)
    runnable.emit(event)
    assert terminal == [event]
    assert not coordinator.is_busy
    assert not coordinator.can_cancel


def test_reservation_cancel_and_stale_empty_ids(qtbot):
    coordinator = TaskCoordinator()
    old = Runnable()
    reservation = coordinator.reserve("导入")
    assert coordinator.reserve("归档") is None
    assert not coordinator.can_cancel
    coordinator.bind(old, ImportPeopleController.connect_signals)
    coordinator.release(reservation)  # cannot release a submitted worker
    assert coordinator.cancel()
    assert not coordinator.cancel()
    assert coordinator.is_busy
    assert old.cancel_calls == ["User requested cancel"]
    old.emit(TaskCancelled("import_people"))
    fresh = Runnable()
    bind(coordinator, fresh)
    events = []
    coordinator.progress.connect(events.append)
    old.emit(TaskCompleted("import_people"))
    old.emit(TaskProgress("import_people", message="old"))
    assert coordinator.active_runnable is fresh
    assert events == []
    coordinator.cancel()
    assert fresh.cancel_calls == ["User requested cancel"]


def test_mismatching_execution_id_is_ignored(qtbot):
    coordinator = TaskCoordinator()
    runnable = Runnable(task_id="actual")
    bind(coordinator, runnable)
    runnable.emit(TaskCompleted("import_people", "other"))
    assert coordinator.is_busy
    runnable.emit(TaskCompleted("import_people", "actual"))
    assert not coordinator.is_busy


def test_worker_delivery_runs_on_coordinator_thread_and_deduplicates(qtbot):
    coordinator = TaskCoordinator()
    runnable = Runnable(task_id="actual")
    bind(coordinator, runnable)
    seen = []
    coordinator.terminal.connect(lambda event: seen.append(QThread.currentThread()))
    event = TaskCompleted("import_people", "actual")
    thread = Thread(target=lambda: (runnable.emit(event), runnable.emit(event)))
    thread.start()
    thread.join()
    assert coordinator.is_busy  # receiver is queued, not an unbound Python closure
    qtbot.waitUntil(lambda: not coordinator.is_busy)
    assert seen == [coordinator.thread()]


def test_terminal_remains_reserved_during_nested_dispatch(qtbot):
    coordinator = TaskCoordinator()
    runnable = Runnable()
    bind(coordinator, runnable)
    seen = []

    def terminal(event):
        seen.append(event)
        assert coordinator.reserve("nested") is None
        runnable.emit(event)
        assert not coordinator.can_cancel

    coordinator.terminal.connect(terminal)
    runnable.emit(TaskCompleted("import_people"))
    assert len(seen) == 1
    assert not coordinator.is_busy


def test_connector_failure_retains_live_worker_until_terminal(qtbot):
    coordinator = TaskCoordinator()
    runnable = Runnable()
    reservation = coordinator.reserve("导入")

    def broken_connector(*args, **kwargs):
        raise RuntimeError("connection failed")

    with pytest.raises(RuntimeError, match="connection failed"):
        coordinator.bind(runnable, broken_connector)
    coordinator.release(reservation)
    assert coordinator.is_busy
    assert coordinator.reserve("new") is None
    runnable.emit(TaskCompleted("import_people"))
    assert not coordinator.is_busy


def test_cancellation_exception_keeps_ownership_and_allows_retry(qtbot, monkeypatch):
    coordinator = TaskCoordinator()
    runnable = Runnable()
    bind(coordinator, runnable)

    def fail(reason):
        raise RuntimeError("cancel unavailable")

    monkeypatch.setattr(runnable, "cancel", fail)
    assert not coordinator.cancel()
    assert coordinator.is_busy
    assert coordinator.can_cancel
    assert not coordinator.is_cancelling
    monkeypatch.setattr(runnable, "cancel", runnable.cancel_calls.append)
    assert coordinator.cancel()
    runnable.emit(TaskCancelled("import_people"))
    assert not coordinator.is_busy
