"""Controller coordinating the scan-and-register photos workflow with the UI."""

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import ScanAndRegisterPhotosCommand, ScanAndRegisterPhotosUseCase
from photo_archiver.workers import QtWorkerExecutor, ScanAndRegisterPhotosTask


class ScanController(QObject):
    """Bridge scan use case requests to worker execution.

    The controller owns no domain logic; it constructs commands and submits
    worker tasks. Views receive the runnable handle and connect their own
    slots via :meth:`connect_signals` so the controller never touches widget
    state and never holds empty slot placeholders.
    """

    def __init__(
        self,
        use_case: ScanAndRegisterPhotosUseCase,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its use case and worker executor."""
        super().__init__(parent)
        self._use_case = use_case
        self._executor = executor

    def scan_folder(self, folder_path: Path, recursive: bool = True, display_name: str | None = None):
        """Start a scan-and-register task and return its runnable handle.

        The returned runnable exposes a ``signals`` attribute the caller uses
        to connect UI slots via :meth:`connect_signals`.
        """
        command = ScanAndRegisterPhotosCommand(
            folder_path=folder_path,
            recursive=recursive,
            folder_display_name=display_name,
        )
        task = ScanAndRegisterPhotosTask(self._use_case, command)
        return self._executor.submit(task)  # type: ignore[arg-type]  # generics variance

    @staticmethod
    def connect_signals(runnable, started: Slot, progress: Slot, completed: Slot, failed: Slot) -> None:
        """Connect the runnable's task signals to the provided UI slots."""
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
