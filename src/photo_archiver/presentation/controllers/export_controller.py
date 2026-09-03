"""Controller coordinating the export workflow with the UI.

Matches the ``ArchiveController`` precedent: export() submits an ExportTask
to the QtWorkerExecutor so long-running exports don't block the UI thread.

阶段 1b 修复（ISSUE-016，ADR-026 §5 同阶段独立提交）：移除 infrastructure.exporters
直接导入 + `_EXPORTERS` 类属性实例化（违反 DEP-002 Presentation MUST NOT import
infrastructure）。format→Exporter 注册表迁 app 装配层（ui_assembly），ExportController
仅依赖 Exporter Protocol + 注入的 exporters dict + format_name 字符串。
"""

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.application.ports.exporter import Exporter
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.workers import ExportTask, QtWorkerExecutor


class ExportController(QObject):
    """Bridge export use case requests to worker execution.

    Holds the ExportService + a format-name → Exporter mapping injected by
    the app 装配层（ui_assembly）so the dialog can pick XLSX / CSV / HTML and
    the controller resolves the concrete exporter at export time（落 B4-a 裁决：
    HTML 走 HtmlExporter 零依赖档）。

    Presentation 不导入 infrastructure.exporters——DEP-002 守护（ISSUE-016 修复）。
    """

    def __init__(
        self,
        service: ExportService,
        exporter: Exporter,
        executor: QtWorkerExecutor,
        exporters: dict[str, Exporter] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with its service, exporter, and worker executor.

        Args:
            service: Application-layer ``ExportService``.
            exporter: Default ``Exporter`` (backward compat for legacy wiring
                that still injects a single exporter; format-aware callers
                should pass ``exporters`` dict + ``format_name`` instead).
            executor: ``QtWorkerExecutor`` to run the export off the UI thread.
            exporters: format-name → Exporter mapping injected by app 装配层
                （ui_assembly 持具体 Exporter 实例化）。None 时仅用 default exporter
                （backward compat for legacy 单 exporter wiring）。
        """
        super().__init__(parent)
        self._service = service
        self._default_exporter = exporter
        self._executor = executor
        self._exporters: dict[str, Exporter] = exporters or {}

    def export(
        self,
        output_path: Path,
        scope: ExportScope = ExportScope.ALL,
        format_name: str | None = None,
        criteria: PhotoSearchCriteria | None = None,
    ):
        """Start an export task and return its runnable handle.

        Args:
            format_name: ``"xlsx"`` / ``"csv"`` / ``"html"`` for exporter lookup.
                When None, falls back to the default exporter injected at construction
                (backward compat for legacy callers that don't pass format).
            criteria: ``PhotoSearchCriteria`` snapshot forwarded into the
                ``ExportTask`` verbatim; consumed only by the ``FILTERED``
                scope (see docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md §3/F5).

        The returned runnable exposes a ``signals`` attribute the caller uses
        to connect UI slots via :meth:`connect_signals`.
        """
        exporter = self._resolve_exporter(format_name)
        task = ExportTask(
            service=self._service,
            exporter=exporter,
            output_path=str(output_path),
            scope=scope,
            criteria=criteria,
        )
        return self._executor.submit(task)  # type: ignore[arg-type]  # generics variance

    def _resolve_exporter(self, format_name: str | None) -> Exporter:
        """Pick the concrete exporter by format name, or fall back to default."""
        if format_name is None:
            return self._default_exporter
        exporter = self._exporters.get(format_name)
        if exporter is None:
            raise ValueError(
                f"Unknown export format '{format_name}'; expected one of {list(self._exporters.keys())}",
            )
        return exporter

    @staticmethod
    def connect_signals(runnable, started: Slot, progress: Slot, completed: Slot, failed: Slot) -> None:
        """Connect the runnable's task signals to the provided UI slots.

        A terminal event that fired before this call is replayed so a
        fast-failing task cannot strand the UI (see QtWorkerRunnable.
        replay_pending_terminal — the macOS CI export race).
        """
        signals = runnable.signals
        signals.started.connect(started)
        signals.progress.connect(progress)
        signals.completed.connect(completed)
        signals.failed.connect(failed)
        # macOS CI race: a fast-failing task can terminate between submit()
        # and this wiring — without the replay its terminal event is lost
        # with no receivers and the UI never re-enables.
        runnable.replay_pending_terminal()
        runnable.replay_pending_terminal()
