"""ClusterFacesController tests — D-4 入口的单飞/取消/接线行为."""

import pytest

pytest.importorskip("PySide6")

from uuid import uuid4

from photo_archiver.presentation.controllers import ClusterFacesController
from photo_archiver.workers import QtWorkerRunnable


class _RecordingExecutor:
    def __init__(self) -> None:
        self.last_task = None
        self.last_command = None
        self.last_runnable = None

    def submit(self, task):
        self.last_task = task
        self.last_command = getattr(task, "_command", None)
        runnable = QtWorkerRunnable(task)
        self.last_runnable = runnable
        return runnable


class _StubUseCase:
    def execute(self, command):  # pragma: no cover - guards against misuse
        raise AssertionError("controller must not execute the use case synchronously")


def _make_controller(use_case=_StubUseCase()):
    executor = _RecordingExecutor()
    controller = ClusterFacesController(use_case=use_case, executor=executor)
    return controller, executor


def test_start_cluster_builds_command_with_run_id():
    controller, executor = _make_controller()
    run_id = uuid4()

    runnable = controller.start_cluster(run_id)

    assert runnable is not None
    assert executor.last_command.recognition_run_id == run_id
    assert executor.last_task.name == "face_clustering"


def test_start_cluster_refuses_while_in_flight_and_releases_on_terminal():
    controller, executor = _make_controller()
    first = controller.start_cluster(uuid4())
    assert first is not None
    assert controller.is_running

    second = controller.start_cluster(uuid4())
    assert second is None
    assert "正在进行" in controller.last_refusal_reason
    assert executor.last_runnable is first

    controller.connect_signals(
        first, lambda _e: None, lambda _e: None, lambda _e: None, lambda _e: None,
    )
    first.signals.completed.emit(object())
    assert not controller.is_running
    assert controller.start_cluster(uuid4()) is not None


def test_start_cluster_refuses_without_use_case():
    controller, executor = _make_controller(use_case=None)

    assert controller.start_cluster(uuid4()) is None
    assert "不可用" in controller.last_refusal_reason
    assert executor.last_task is None


def test_connect_signals_wires_five_channels():
    controller, _ = _make_controller()
    runnable = controller.start_cluster(uuid4())
    received: list[str] = []
    controller.connect_signals(
        runnable,
        lambda _e: received.append("started"),
        lambda _e: received.append("progress"),
        lambda _e: received.append("completed"),
        lambda _e: received.append("failed"),
        cancelled=lambda _e: received.append("cancelled"),
    )

    runnable.signals.started.emit(object())
    runnable.signals.progress.emit(object())
    runnable.signals.failed.emit(object())
    runnable.signals.cancelled.emit(object())

    assert received == ["started", "progress", "failed", "cancelled"]


def test_stale_terminal_does_not_release_new_guard():
    controller, _ = _make_controller()
    first = controller.start_cluster(uuid4())
    controller.connect_signals(
        first, lambda _e: None, lambda _e: None, lambda _e: None, lambda _e: None,
    )
    first.signals.cancelled.emit(object())
    second = controller.start_cluster(uuid4())
    assert second is not None and second is not first

    first.signals.cancelled.emit(object())

    assert controller.is_running
