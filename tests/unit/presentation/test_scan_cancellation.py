"""P0-4-A cancellation tests for the Scan workflow (real UI chain).

The cancelled terminal path was previously unwired for scans: the Cancel
Task action set the cooperative flag, the task eventually emitted
``cancelled`` — and the MainWindow never connected that signal, leaving the
UI stuck at "Cancelling ...".

These tests cover the P0-4-A contract at two levels:

- MainWindow wiring (synthetic terminal emissions, main thread — the proven
  ``test_match_ui_wiring`` pattern): the cancelled slot resets the Cancel
  button/progress/status and re-enables the Scan action.
- Real executor (real QThreadPool + SQLite + 400-file workload): cancelling
  a scan that is demonstrably in flight ends in the cancelled terminal state
  and the UI recovers; a follow-up scan can start (cross scenario).

Cancellation granularity is the task boundary (LIMIT-002 design analog):
the use case finishes its current batch, then the task reports cancelled.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from pathlib import Path

from PIL import Image

from photo_archiver.app import bootstrap_application
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import TaskCancelled

FILE_COUNT = 2000


def _make_photo_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "photos"
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(FILE_COUNT):
        Image.new("RGB", (16, 16), (i % 255, 40, 90)).save(folder / f"p{i:04d}.png")
    return folder


def _build_window(qtbot, tmp_path: Path) -> MainWindow:
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'cancel.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    return window


def test_cancelled_terminal_resets_ui_and_reenables_scan(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """The P0-4-A core wiring: cancelled resets Cancel/progress/status + Scan."""
    window = _build_window(qtbot, tmp_path)
    photo_dir = _make_photo_dir(tmp_path)

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(photo_dir),
    )

    # Real user entry: the scan starts and enters its single-flight state.
    window._scan_action.trigger()
    qtbot.waitUntil(lambda: not window._scan_action.isEnabled(), timeout=10000)
    assert window._cancel_action.isEnabled()
    assert "正在扫描" in window._status_label.text()

    # Real user entry for cancellation: press the toolbar Cancel Task action.
    window._cancel_action.trigger()
    assert window._active_runnable is not None
    assert window._active_runnable.task.is_cancel_requested

    # The task reports the cancelled terminal state (boundary granularity).
    runnable = window._active_runnable
    runnable.signals.cancelled.emit(
        TaskCancelled("scan_and_register_photos", "task_1", "User requested cancel")
    )
    assert "已取消" in window._status_label.text().lower()
    assert not window._cancel_action.isEnabled()
    assert window._scan_action.isEnabled()


def test_scan_refusal_surfaces_reason_through_real_ui(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """A second scan attempt mid-flight surfaces the refusal in the status bar."""
    window = _build_window(qtbot, tmp_path)
    photo_dir = _make_photo_dir(tmp_path)

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(photo_dir),
    )
    window._scan_action.trigger()
    qtbot.waitUntil(lambda: not window._scan_action.isEnabled(), timeout=10000)

    # Second attempt: re-enable the action first to simulate the disable
    # being bypassed — the controller-level guard must still refuse (§17:
    # system-level single-flight, not just a disabled button).
    window._scan_action.setEnabled(True)
    window._scan_action.trigger()
    assert "正在进行" in window._status_label.text().lower()
    assert window._scan_controller.is_running
    window._scan_action.setEnabled(False)

    # The first scan completes; the action re-enables (no permanent lockout).
    qtbot.waitUntil(lambda: window._scan_action.isEnabled(), timeout=60000)
    assert not window._cancel_action.isEnabled()


def test_real_cancelled_scan_reports_cancelled_terminal_and_recovers(
    qtbot, tmp_path: Path
) -> None:
    """Real executor: cancel an in-flight scan, then start a follow-up scan."""
    window = _build_window(qtbot, tmp_path)
    photo_dir = _make_photo_dir(tmp_path)

    # Headless check without the picker (the picker path is covered by the
    # monkeypatched tests above and by the manual desktop smoke).
    runnable1 = window._scan_controller.scan_folder(photo_dir)
    assert runnable1 is not None
    window._connect_scan_signals(runnable1)
    assert not window._scan_action.isEnabled()

    # Cancel while the workload is still running (400 files give a wide
    # margin before the boundary check reports the terminal state).
    runnable1.cancel("User requested cancel")
    assert runnable1.task.is_cancel_requested

    qtbot.waitUntil(
        lambda: "已取消" in window._status_label.text().lower(),
        timeout=60000,
    )
    assert window._scan_action.isEnabled()
    assert not window._scan_controller.is_running

    # Cross scenario: the follow-up scan starts and completes normally.
    runnable2 = window._scan_controller.scan_folder(photo_dir)
    assert runnable2 is not None
    window._connect_scan_signals(runnable2)
    qtbot.waitUntil(
        lambda: window._scan_action.isEnabled()
        and not window._scan_controller.is_running,
        timeout=60000,
    )
