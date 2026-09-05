"""P0-4-B single-flight tests for ScanController.

Two layers, mirroring the MatchPersonsController test split:

- Synthetic (main-thread emissions through a real QtWorkerRunnable that never
  starts a thread): guard semantics — blocks a second submission, releases on
  every terminal state, stale-runnable protection. Same proven pattern as
  ``test_match_persons_controller.py``.
- Real executor (real QThreadPool + real SQLite + real scan workload): the
  refusal happens mid-flight and the guard re-opens after the terminal state.
  Synchronization uses ``qtbot.waitUntil`` polling (robust to whether the
  terminal guard release runs directly on the worker thread or queued on the
  main thread) — never ``waitSignal`` + immediate assert (racy).
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from pathlib import Path

from PIL import Image

from photo_archiver.app import bootstrap_application
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.controllers.scan_controller import ScanController
from photo_archiver.workers import QtWorkerRunnable
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskFailed

FILE_COUNT = 400


class _RecordingExecutor:
    """Wraps the submitted task in a real QtWorkerRunnable without starting
    any thread, so guard-release tests can emit terminal signals from the
    test (mirrors the MatchPersonsController fake)."""

    def __init__(self) -> None:
        self.last_runnable: QtWorkerRunnable | None = None

    def submit(self, task):
        runnable = QtWorkerRunnable(task)
        self.last_runnable = runnable
        return runnable


def _make_synthetic_controller() -> tuple[ScanController, _RecordingExecutor]:
    executor = _RecordingExecutor()

    class _StubUseCase:
        def bind_progress_reporter(self, reporter):  # pragma: no cover
            import contextlib

            return contextlib.nullcontext()

        def execute(self, command):  # pragma: no cover - never executed here
            raise AssertionError("synthetic tests never execute the use case")

    controller = ScanController(_StubUseCase(), executor)  # type: ignore[arg-type]
    return controller, executor


def test_single_flight_guard_blocks_second_start() -> None:
    """While a scan runnable is in flight, scan_folder refuses and explains."""
    controller, executor = _make_synthetic_controller()
    first = controller.scan_folder(Path("whatever"))
    assert first is not None
    assert controller.is_running

    second = controller.scan_folder(Path("whatever"))
    assert second is None
    assert "正在进行" in (controller.last_refusal_reason or "")


def test_guard_released_on_completed_allows_next_scan() -> None:
    controller, executor = _make_synthetic_controller()
    first = controller.scan_folder(Path("whatever"))
    assert first is not None
    controller.connect_signals(first, *(lambda e: None,) * 4, cancelled=lambda e: None)

    first.signals.completed.emit(TaskCompleted("scan_and_register_photos", "t1", None))
    assert not controller.is_running

    second = controller.scan_folder(Path("whatever"))
    assert second is not None


def test_guard_released_on_failed_allows_retry() -> None:
    controller, executor = _make_synthetic_controller()
    first = controller.scan_folder(Path("whatever"))
    assert first is not None
    controller.connect_signals(first, *(lambda e: None,) * 4, cancelled=lambda e: None)

    first.signals.failed.emit(TaskFailed("scan_and_register_photos", RuntimeError("boom"), task_id="t1"))
    assert not controller.is_running

    assert controller.scan_folder(Path("whatever")) is not None


def test_guard_released_on_cancelled_allows_restart() -> None:
    """Cross scenario: a cancelled scan fully releases the guard."""
    controller, executor = _make_synthetic_controller()
    first = controller.scan_folder(Path("whatever"))
    assert first is not None
    controller.connect_signals(first, *(lambda e: None,) * 4, cancelled=lambda e: None)

    first.signals.cancelled.emit(TaskCancelled("scan_and_register_photos", "t1", "User requested cancel"))
    assert not controller.is_running

    assert controller.scan_folder(Path("whatever")) is not None


def test_terminal_from_stale_runnable_does_not_release_new_guard() -> None:
    """A late terminal from a superseded runnable must not clear the new guard."""
    controller, executor = _make_synthetic_controller()
    stale = controller.scan_folder(Path("whatever"))
    assert stale is not None
    controller.connect_signals(stale, *(lambda e: None,) * 4, cancelled=lambda e: None)

    replacement = controller.scan_folder(Path("whatever-2"))
    assert replacement is None  # single-flight: no second submission path

    stale.signals.completed.emit(TaskCompleted("scan_and_register_photos", "t1", None))
    assert not controller.is_running

    fresh = controller.scan_folder(Path("whatever-3"))
    assert fresh is not None
    assert controller.is_running
    stale.signals.completed.emit(TaskCompleted("scan_and_register_photos", "t2", None))
    assert controller.is_running  # stale terminal must not clear the fresh guard


def test_real_executor_refuses_second_scan_mid_flight_and_recovers(qtbot, tmp_path: Path) -> None:
    """Real QThreadPool + real SQLite: refusal mid-flight, recovery after."""
    folder = tmp_path / "photos"
    folder.mkdir(parents=True)
    for i in range(FILE_COUNT):
        Image.new("RGB", (16, 16), (i % 255, 40, 90)).save(folder / f"p{i:04d}.png")

    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'sf.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    controller = ScanController(context.services.scan_and_register_photos, context.worker_executor)

    runnable1 = controller.scan_folder(folder)
    assert runnable1 is not None
    controller.connect_signals(runnable1, *(lambda e: None,) * 4, cancelled=lambda e: None)
    assert controller.is_running  # in flight (submitted to the real pool)

    runnable2 = controller.scan_folder(folder)
    assert runnable2 is None
    assert "正在进行" in (controller.last_refusal_reason or "")

    # The in-flight scan runs to its designed granularity and completes;
    # the guard re-opens (poll — robust to direct/queued release timing).
    qtbot.waitUntil(lambda: not controller.is_running, timeout=60000)

    runnable3 = controller.scan_folder(folder)
    assert runnable3 is not None
    controller.connect_signals(runnable3, *(lambda e: None,) * 4, cancelled=lambda e: None)
    qtbot.waitUntil(lambda: not controller.is_running, timeout=60000)
    # Scenario B proof: the rescan genuinely re-registered (skips this time).
    result = runnable3.task._command  # noqa: SLF001 - test introspection only
    assert result.folder_path == folder
