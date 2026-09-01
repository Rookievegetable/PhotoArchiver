"""ExportWorker — 长耗时导出不阻塞 UI 主线程。

Worker 通用执行器框架（QtWorkerExecutor）下，ExportTask 封装 ExportService
的导出调用。粗粒度两阶段进度：收集数据 → 写入文件。
"""

from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.services.export_service import ExportService
from photo_archiver.application.ports.exporter import Exporter
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.workers.task import WorkerTask


class ExportTask(WorkerTask[str]):
    """Run the export use case inside a worker task.

    Follows the ``ArchivePhotosTask`` precedent: two coarse progress updates
    (gathering data / writing file) rather than per-item streaming, since the
    export operation is batch-oriented and the data size is small enough that
    fine-grained progress would add overhead without value.
    """

    def __init__(
        self,
        service: ExportService,
        exporter: Exporter,
        output_path: str,
        scope: ExportScope = ExportScope.ALL,
        criteria: PhotoSearchCriteria | None = None,
    ) -> None:
        """Initialize the task with its service, exporter, and scope.

        Args:
            service: Application-layer ExportService.
            exporter: Concrete exporter (Excel/CSV).
            output_path: Where to write the export file.
            scope: Data scope (default ALL).
            criteria: ``PhotoSearchCriteria`` snapshot for the ``FILTERED``
                scope (default None; consumed only by the FILTERED path —
                see docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md §3/F5).
        """
        super().__init__("export")
        self._service = service
        self._exporter = exporter
        self._output_path = output_path
        self._scope = scope
        self._criteria = criteria

    def execute(self) -> str:
        """Execute the export, streaming two-phase progress."""
        self.raise_if_cancelled()
        self.report_progress("Gathering export data")
        result = self._service.export(
            self._exporter, self._output_path, self._scope, criteria=self._criteria
        )
        self.raise_if_cancelled()
        self.report_progress("Export finished", current=1, total=1)
        return result
