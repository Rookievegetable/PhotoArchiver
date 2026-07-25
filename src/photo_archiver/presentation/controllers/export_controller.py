"""Controller coordinating the export workflow with the UI.

Matches the ``ArchiveController`` precedent: export() submits an ExportTask
to the QtWorkerExecutor so long-running exports don't block the UI thread.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.application.ports.exporter import Exporter
from photo_archiver.workers import ExportTask, QtWorkerExecutor


class ExportController(QObject):
    """Bridge export use case requests to worker execution.

    The controller holds the ExportService and a concrete Exporter (Excel/CSV)
    so the dialog only needs to choose scope and output path.
    """

    def __init__(
        self,
        service: ExportService,
        exporter: Exporter,
        executor: QtWorkerExecutor,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its service, exporter, and worker executor.

        Args:
            service: Application-layer ``ExportService``.
            exporter: Concrete ``Exporter`` (e.g. ``ExcelExporter``).
            executor: ``QtWorkerExecutor`` to run the export off the UI thread.
        """
        super().__init__(parent)
        self._service = service
        self._exporter = exporter
        self._executor = executor

    def export(
        self,
        output_path: Path,
        scope: ExportScope = ExportScope.ALL,
    ):
        """Start an export task and return its runnable handle.

        The returned runnable exposes a ``signals`` attribute the caller uses
        to connect UI slots via :meth:`connect_signals`.
        """
        task = ExportTask(
            service=self._service,
            exporter=self._exporter,
            output_path=str(output_path),
            scope=scope,
        )
        return self._executor.submit(task)  # type: ignore[arg-type]  # generics variance

    @staticmethod
    def connect_signals(runnable, started: Slot, progress: Slot, completed: Slot, failed: Slot) -> None:
        """Connect the runnable's task signals to the provided UI slots."""
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
