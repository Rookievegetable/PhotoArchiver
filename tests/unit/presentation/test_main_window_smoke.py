"""Smoke tests for MainWindow and controller wiring (Step 12 expanded)."""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

# Import the app package first so its __init__ finishes initializing before
# MainWindow pulls app.context.ApplicationContext during its own import.
from photo_archiver.app import bootstrap_application  # noqa: F401
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.controllers import (
    ArchiveController,
    ImportPeopleController,
    ReviewController,
    ScanController,
)
from photo_archiver.presentation.views.main_window import MainWindow


def test_main_window_constructs_with_context(qtbot, tmp_path: Path) -> None:
    """MainWindow should construct with the full Step 12 controller set."""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'smoke.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    assert window.windowTitle() == "PhotoArchiver"
    assert window.centralWidget() is not None


def test_main_window_exposes_four_controllers(qtbot, tmp_path: Path) -> None:
    """MainWindow should assemble scan/import/archive/review controllers."""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'smoke2.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    assert isinstance(window._scan_controller, ScanController)
    assert isinstance(window._import_controller, ImportPeopleController)
    assert isinstance(window._archive_controller, ArchiveController)
    assert isinstance(window._review_controller, ReviewController)


def test_scan_controller_connect_signals_wires_slots(qtbot) -> None:
    """ScanController.connect_signals should connect runnable signals to provided slots."""
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

        def replay_pending_terminal(self) -> None:
            """Interface parity with QtWorkerRunnable (no-op: no terminal retained)."""

    runnable = FakeRunnable()
    called: list = []

    controller = ScanController(use_case=None, executor=None)  # type: ignore[arg-type]
    controller.connect_signals(
        runnable,
        started=lambda e: called.append("started"),
        progress=lambda e: called.append("progress"),
        completed=lambda e: called.append("completed"),
        failed=lambda e: called.append("failed"),
    )
    runnable.signals.started.emit(None)
    assert called == ["started"]
