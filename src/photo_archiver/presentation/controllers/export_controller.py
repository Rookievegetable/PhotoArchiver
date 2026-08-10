"""Controller coordinating the export workflow with the UI.

Matches the ``ArchiveController`` precedent: export() submits an ExportTask
to the QtWorkerExecutor so long-running exports don't block the UI thread.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.application.ports.exporter import Exporter
from photo_archiver.infrastructure.exporters import (
    CsvExporter,
    ExcelExporter,
    HtmlExporter,
)
from photo_archiver.workers import ExportTask, QtWorkerExecutor


class ExportController(QObject):
    """Bridge export use case requests to worker execution.

    Holds the ExportService and a format-name → Exporter mapping so the dialog
    can pick XLSX / CSV / HTML and the controller resolves the concrete exporter
    at export time (落 B4-a 裁决：HTML 走 HtmlExporter 零依赖档）。
    """

    # format name → concrete Exporter instance（B4 扩 HtmlExporter）。
    _EXPORTERS: dict[str, Exporter] = {
        "xlsx": ExcelExporter(),
        "csv": CsvExporter(),
        "html": HtmlExporter(),
    }

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
            exporter: Default ``Exporter`` (backward compat for legacy wiring
                that still injects a single exporter; format-aware callers
                should pass ``export`` a ``format_name`` instead).
            executor: ``QtWorkerExecutor`` to run the export off the UI thread.
        """
        super().__init__(parent)
        self._service = service
        self._default_exporter = exporter
        self._executor = executor

    def export(
        self,
        output_path: Path,
        scope: ExportScope = ExportScope.ALL,
        format_name: str | None = None,
    ):
        """Start an export task and return its runnable handle.

        Args:
            format_name: ``"xlsx"`` / ``"csv"`` / ``"html"`` for exporter lookup.
                When None, falls back to the default exporter injected at construction
                (backward compat for legacy callers that don't pass format).

        The returned runnable exposes a ``signals`` attribute the caller uses
        to connect UI slots via :meth:`connect_signals`.
        """
        exporter = self._resolve_exporter(format_name)
        task = ExportTask(
            service=self._service,
            exporter=exporter,
            output_path=str(output_path),
            scope=scope,
        )
        return self._executor.submit(task)  # type: ignore[arg-type]  # generics variance

    def _resolve_exporter(self, format_name: str | None) -> Exporter:
        """Pick the concrete exporter by format name, or fall back to default."""
        if format_name is None:
            return self._default_exporter
        exporter = self._EXPORTERS.get(format_name)
        if exporter is None:
            raise ValueError(
                f"Unknown export format '{format_name}'; expected one of {list(self._EXPORTERS.keys())}",
            )
        return exporter

    @staticmethod
    def connect_signals(runnable, started: Slot, progress: Slot, completed: Slot, failed: Slot) -> None:
        """Connect the runnable's task signals to the provided UI slots."""
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
