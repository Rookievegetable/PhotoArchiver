"""Controller coordinating the people-import workflow with the UI."""

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from photo_archiver.application import ImportPeopleCommand, ImportPeopleUseCase
from photo_archiver.workers import ImportPeopleTask, QtWorkerExecutor


class ImportPeopleController(QObject):
    """Bridge people-import use case requests to worker execution.

    The controller owns no domain logic; it constructs commands and submits
    worker tasks. Views receive the runnable handle and connect their own
    slots via :meth:`connect_signals` so the controller never touches widget
    state.
    """

    def __init__(
        self,
        use_case: ImportPeopleUseCase,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its use case and worker executor."""
        super().__init__(parent)
        self._use_case = use_case
        self._executor = executor

    def import_from(
        self,
        source_path: Path,
        has_header: bool = True,
        sheet_name: str | None = None,
    ):
        """Start an import-people task and return its runnable handle.

        The returned runnable exposes a ``signals`` attribute the caller uses
        to connect UI slots via :meth:`connect_signals`.
        """
        command = ImportPeopleCommand(
            source_path=source_path,
            has_header=has_header,
            sheet_name=sheet_name,
        )
        task = ImportPeopleTask(self._use_case, command)
        return self._executor.submit(task)  # type: ignore[arg-type]  # WorkerTask[ImportPeopleResult] vs [object] generics variance

    @staticmethod
    def connect_signals(runnable, started: Slot, progress: Slot, completed: Slot, failed: Slot) -> None:
        """Connect the runnable's task signals to the provided UI slots.

        Reuses the same signal-shape as ScanController so MainWindow can
        dispatch with a single helper without per-controller adapters.
        """
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
