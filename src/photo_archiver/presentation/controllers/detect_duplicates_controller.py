"""Controller coordinating duplicate detection with the UI (B1 重复图片检测).

首版只读：本 controller 仅编排 ``DetectDuplicatesService.execute()`` 拿
``DuplicateReport`` 并交由 ``DuplicateReportDialog`` 展示，不触发任何删除
或归档操作。删除用户文件属高危操作（ai-rules §20 安全规则），留后续版本裁决。

查询走同步——查重是快速仓储查询（SQL 下推，<50ms 可同步），
不沉 Worker；若万级照片实测慢再下沉（WRK-001）。
"""

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from loguru import logger

from photo_archiver.application.dtos import DuplicateReport
# DetectDuplicatesService currently has no dedicated Protocol in application/use_cases/.
# Import the concrete service at the Protocol boundary — DEP-010 allows Presentation
# to depend on Application; the service is the use case surface. A formal Protocol
# can be split out later if a second implementation appears (YAGNI today).
from photo_archiver.application.services import DetectDuplicatesService
from photo_archiver.presentation.ui_text import (
    DUPLICATE_FAILED_MESSAGE,
    DUPLICATE_FAILED_TITLE,
)
from photo_archiver.presentation.views.duplicate_report_dialog import (
    DuplicateReportDialog,
)


class DetectDuplicatesController(QObject):
    """Bridge the duplicate detection use case to the UI.

    The controller is a thin coordinator: it calls the service synchronously
    (fast repository query), then surfaces the resulting ``DuplicateReport``
    via the ``DuplicateReportDialog``. No worker submission in this version
    because duplicate grouping is SQL push-down, not long-running I/O.
    """

    def __init__(
        self,
        service: DetectDuplicatesService,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with the duplicate detection service.

        Args:
            service: The ``DetectDuplicatesService`` assembled in
                ``app/services.py`` — already wired to the runtime photo repository.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._service = service

    @Slot()
    def detect_and_show(self) -> None:
        """Run the duplicate detection and pop up the report dialog.

        Synchronous on the UI thread: the repository query is fast (SQL
        push-down). Errors are logged via Loguru and
        surfaced to the user as a critical message box — the use case never
        raises in normal operation, so any exception here is unexpected.
        """
        try:
            report: DuplicateReport = self._service.execute()
        except Exception as exc:  # noqa: BLE001  # UI boundary: show the user, log the detail
            logger.exception("Duplicate detection failed unexpectedly")
            parent_widget = self.parent()
            target = parent_widget if isinstance(parent_widget, QWidget) else None
            QMessageBox.critical(
                target,
                DUPLICATE_FAILED_TITLE,
                DUPLICATE_FAILED_MESSAGE.format(detail=exc),
            )
            return
        # dialog 期望 QWidget parent；controller 的 self.parent() 返 QObject，经
        # isinstance 防护降为 QWidget | None（与 B-6 注解统一对齐）
        parent_widget = self.parent()
        qt_parent = parent_widget if isinstance(parent_widget, QWidget) else None
        dialog = DuplicateReportDialog(report, parent=qt_parent)
        dialog.exec()
