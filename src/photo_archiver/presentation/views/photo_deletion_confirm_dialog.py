"""Photo deletion confirmation dialog — Phase E E-4（ADR-034 D1/D3 确认流）.

消费 ``DeletePhotosUseCase.preview()`` 产的 ``PhotoDeletionPreview``，展示
级联计数（识别/归档）与 **"仅移除库内登记，不删除磁盘文件"明示**（D3 强制
文案）。纯展示视图——持有 DTO 不持服务，确认与否经模态结果返回调用方
（MainWindow），与 ``ArchivePreviewDialog`` 同模式。
"""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.presentation.ui_text import (
    DELETE_PHOTOS_CONFIRM,
    DELETE_PHOTOS_CONFIRM_BUTTON,
    DELETE_PHOTOS_MISSING_NOTE,
    DELETE_PHOTOS_TITLE,
)

if TYPE_CHECKING:
    from photo_archiver.application.dtos import PhotoDeletionPreview


class PhotoDeletionConfirmDialog(QDialog):
    """Render the cascade-count preview and ask for explicit confirmation.

    Accepting (OK /「移除登记」) means the user confirmed the deletion shown
    in the preview; rejecting cancels. The dialog never calls the use case
    itself — MainWindow orchestrates preview → dialog → execute.
    """

    def __init__(
        self,
        preview: "PhotoDeletionPreview",
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog with the preview to confirm.

        Args:
            preview: The ``PhotoDeletionPreview`` returned by
                ``DeletePhotosUseCase.preview`` — its counters drive the text.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(DELETE_PHOTOS_TITLE)
        self.setMinimumWidth(420)
        self._preview = preview
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out the confirmation text and the OK/Cancel button box."""
        layout = QVBoxLayout(self)

        message = QLabel(self._confirmation_text())
        message.setWordWrap(True)
        layout.addWidget(message)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(DELETE_PHOTOS_CONFIRM_BUTTON)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _confirmation_text(self) -> str:
        """Return the cascade-count text with the mandatory D3 disk disclaimer."""
        text = DELETE_PHOTOS_CONFIRM.format(
            photo_count=self._preview.photo_count,
            recognition_count=self._preview.recognition_count,
            archive_count=self._preview.archive_count,
        )
        if self._preview.missing_count:
            text += "\n\n" + DELETE_PHOTOS_MISSING_NOTE.format(
                missing_count=self._preview.missing_count,
            )
        return text
