"""Main application window."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStatusBar,
    QToolBar,
)

from photo_archiver.app.context import ApplicationContext
from photo_archiver.presentation.controllers import ScanController
from photo_archiver.workers.events import TaskCompleted, TaskFailed, TaskProgress, TaskStarted

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800

_PROGRESS_RESOLUTION = 100


class MainWindow(QMainWindow):
    """Main window for the PhotoArchiver desktop application.

    The window owns no business logic; it delegates button actions to a
    :class:`ScanController` and reflects worker task events in widgets.
    """

    def __init__(self, context: ApplicationContext) -> None:
        """Initialize the main window with the runtime application context.

        Args:
            context: Assembled runtime context providing services and worker executor.
        """
        super().__init__()
        self.setWindowTitle("PhotoArchiver")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self._context = context
        self._scan_controller = ScanController(
            context.services.scan_and_register_photos,
            context.worker_executor,
            parent=self,
        )

        self._build_toolbar()
        self._build_central()
        self._build_status()

    def _build_toolbar(self) -> None:
        """Create the primary action toolbar."""
        toolbar = QToolBar("Main", self)
        self.addToolBar(toolbar)

        scan_action = QAction("Scan Folder", self)
        scan_action.triggered.connect(self._on_scan_clicked)
        toolbar.addAction(scan_action)

    def _build_central(self) -> None:
        """Create the central progress placeholder."""
        self._progress = QProgressBar(self)
        self._progress.setRange(0, _PROGRESS_RESOLUTION)
        self._progress.setValue(0)
        self.setCentralWidget(self._progress)

    def _build_status(self) -> None:
        """Create the status bar with a persistent status label."""
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status_label = QLabel("Ready", self)
        self._status.addWidget(self._status_label)

    def _on_scan_clicked(self) -> None:
        """Open a folder picker and start the scan workflow."""
        folder = QFileDialog.getExistingDirectory(self, "Select Photo Folder")
        if not folder:
            return
        self._progress.setValue(0)
        self._status_label.setText(f"Scanning {folder} ...")
        self._scan_controller.scan_folder(Path(folder))
        if self._scan_controller._current_runnable is not None:
            self._scan_controller.wire(self._scan_controller._current_runnable)
            signals = self._scan_controller._current_runnable.signals
            signals.started.connect(self._on_started)
            signals.progress.connect(self._on_progress)
            signals.completed.connect(self._on_completed)
            signals.failed.connect(self._on_failed)

    def _on_started(self, event: TaskStarted) -> None:
        """Reflect task start in the status bar."""
        self._status_label.setText("Scan started ...")

    def _on_progress(self, event: TaskProgress) -> None:
        """Update the progress bar from task progress events."""
        if event.current is not None and event.total and event.total > 0:
            self._progress.setValue(int(event.current * _PROGRESS_RESOLUTION / event.total))

    def _on_completed(self, event: TaskCompleted) -> None:
        """Reflect task completion and surface result statistics."""
        result = event.result
        message = (
            f"Scan complete: discovered={result.discovered_count}, "
            f"registered={result.registered_count}, skipped={result.skipped_count}, "
            f"failed={result.failed_count}"
        )
        self._status_label.setText(message)
        self._progress.setValue(_PROGRESS_RESOLUTION)

    def _on_failed(self, event: TaskFailed) -> None:
        """Surface task failure in a modal and reset progress."""
        self._progress.setValue(0)
        self._status_label.setText("Scan failed.")
        QMessageBox.warning(self, "Scan Failed", str(event.error))
