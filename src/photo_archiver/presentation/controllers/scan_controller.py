"""Controller coordinating the scan-and-register photos workflow with the UI."""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import ScanAndRegisterPhotosCommand, ScanAndRegisterPhotosUseCase
from photo_archiver.workers import QtWorkerExecutor, ScanAndRegisterPhotosTask
from photo_archiver.workers.events import TaskCompleted, TaskFailed, TaskProgress, TaskStarted


class ScanController(QObject):
    """Bridge scan use case requests to worker execution and surface events to the UI.

    The controller owns no domain logic; it constructs commands, submits worker
    tasks, and re-emits task events as Qt signals that views connect to without
    touching either the application or worker layers directly.
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
        self._current_runnable = None

    def scan_folder(self, folder_path: Path, recursive: bool = True, display_name: str | None = None) -> None:
        """Start a scan-and-register task for the given folder."""
        command = ScanAndRegisterPhotosCommand(
            folder_path=folder_path,
            recursive=recursive,
            folder_display_name=display_name,
        )
        task = ScanAndRegisterPhotosTask(self._use_case, command)
        self._current_runnable = self._executor.submit(task)

    @Slot(object)
    def on_started(self, event: TaskStarted) -> None:
        """Handle task started events (wired by views)."""
        return None

    @Slot(object)
    def on_progress(self, event: TaskProgress) -> None:
        """Handle task progress events (wired by views)."""
        return None

    @Slot(object)
    def on_completed(self, event: TaskCompleted) -> None:
        """Handle task completed events (wired by views)."""
        return None

    @Slot(object)
    def on_failed(self, event: TaskFailed) -> None:
        """Handle task failed events (wired by views)."""
        return None

    def wire(self, runnable) -> None:
        """Connect the current runnable's signals to this controller's slots."""
        signals = runnable.signals
        signals.started.connect(self.on_started)
        signals.progress.connect(self.on_progress)
        signals.completed.connect(self.on_completed)
        signals.failed.connect(self.on_failed)
