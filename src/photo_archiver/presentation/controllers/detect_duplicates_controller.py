"""Controller coordinating duplicate detection with the UI (B1 + Phase E E-4).

本 controller 编排 ``DetectDuplicatesService.execute()`` 拿 ``DuplicateReport``
并交由 ``DuplicateReportDialog`` 展示。注入 ``DisposeDuplicatesUseCase``（E-4）
后，用户在报告对话框点「按建议处置」→ controller 二次确认（级联计数预览）
→ 执行处置（每组保留最早注册、其余移除登记，磁盘文件不动）。

查询走同步——查重是快速仓储查询（SQL 下推，<50ms 可同步），
不沉 Worker；若万级照片实测慢再下沉（WRK-001）。
"""

from typing import cast

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox, QWidget

from loguru import logger

from photo_archiver.application.commands import DisposeDuplicatesCommand
from photo_archiver.application.dtos import DuplicateReport
# DetectDuplicatesService currently has no dedicated Protocol in application/use_cases/.
# Import the concrete service at the Protocol boundary — DEP-010 allows Presentation
# to depend on Application; the service is the use case surface. A formal Protocol
# can be split out later if a second implementation appears (YAGNI today).
from photo_archiver.application.services import DetectDuplicatesService
from photo_archiver.application.use_cases import DisposeDuplicatesUseCase
from photo_archiver.presentation.ui_text import (
    DUPLICATE_DISPOSE_CONFIRM,
    DUPLICATE_DISPOSE_CONFIRM_TITLE,
    DUPLICATE_DISPOSE_DONE,
    DUPLICATE_DISPOSE_NONE,
    DUPLICATE_FAILED_MESSAGE,
    DUPLICATE_FAILED_TITLE,
)
from photo_archiver.presentation.views.duplicate_report_dialog import (
    DuplicateReportDialog,
)


class DetectDuplicatesController(QObject):
    """Bridge the duplicate detection (and disposal) use cases to the UI.

    The controller is a thin coordinator: it calls the detection service
    synchronously (fast repository query), then surfaces the resulting
    ``DuplicateReport`` via the ``DuplicateReportDialog``. When a disposal
    use case is wired (E-4) and the user accepts the report dialog, it runs
    preview → confirm → execute for the disposal (D6 semantics).
    """

    def __init__(
        self,
        service: DetectDuplicatesService,
        disposal: DisposeDuplicatesUseCase | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller with the detection (and disposal) services.

        Args:
            service: The ``DetectDuplicatesService`` assembled in
                ``app/services.py`` — already wired to the runtime photo repository.
            disposal: Optional ``DisposeDuplicatesUseCase`` (E-4). ``None`` keeps
                the report dialog read-only (legacy/CLI wiring).
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._service = service
        self._disposal = disposal

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
                self._target(target),
                DUPLICATE_FAILED_TITLE,
                DUPLICATE_FAILED_MESSAGE.format(detail=exc),
            )
            return
        # dialog 期望 QWidget parent；controller 的 self.parent() 返 QObject，经
        # isinstance 防护降为 QWidget | None（与 B-6 注解统一对齐）
        parent_widget = self.parent()
        qt_parent = parent_widget if isinstance(parent_widget, QWidget) else None
        dialog = DuplicateReportDialog(report, parent=qt_parent, disposal=self._disposal)
        if not dialog.exec():
            return
        self._dispose_confirmed()

    def _dispose_confirmed(self) -> None:
        """Preview the disposal, ask for final confirmation, then execute (D6)."""
        parent_widget = self.parent()
        qt_parent = parent_widget if isinstance(parent_widget, QWidget) else None
        if self._disposal is None:  # unreachable: accept requires a wired disposal
            return
        preview = self._disposal.preview()
        if preview.is_empty:
            QMessageBox.information(self._target(qt_parent), DUPLICATE_DISPOSE_CONFIRM_TITLE, DUPLICATE_DISPOSE_NONE)
            return
        confirm = QMessageBox.question(
            self._target(qt_parent),
            DUPLICATE_DISPOSE_CONFIRM_TITLE,
            DUPLICATE_DISPOSE_CONFIRM.format(
                group_count=preview.group_count,
                photo_count=preview.photo_count,
                recognition_count=preview.recognition_count,
                archive_count=preview.archive_count,
            ),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        removable_ids = tuple(
            pid for group in preview.groups for pid in group.remove_photo_ids
        )
        result = self._disposal.execute(DisposeDuplicatesCommand(photo_ids=removable_ids))
        QMessageBox.information(
            self._target(qt_parent),
            DUPLICATE_DISPOSE_CONFIRM_TITLE,
            DUPLICATE_DISPOSE_DONE.format(
                removed=result.removed,
                groups_affected=result.groups_affected,
                rejected=result.rejected,
            ),
        )

    @staticmethod
    def _target(qt_parent: QWidget | None) -> QWidget:
        """Return the message-box parent widget for QMessageBox static calls.

        PySide6 6.8.3 stubs type the static-method parent as a non-optional
        ``QWidget`` even though Qt accepts a null parent at runtime; the cast
        keeps the documented "parent may be absent" behaviour type-honest
        under those stubs.
        """
        return cast(QWidget, qt_parent)
