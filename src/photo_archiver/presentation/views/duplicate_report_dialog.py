"""Duplicate report dialog for B1 重复图片检测.

首版只读：分组列表展示重复照片（按 content_hash 分组，每组列出成员路径），
不提供删除按钮——删除用户文件属高危操作（ai-rules §20 安全规则），留后续版本
裁决。复刻既有 ArchivePreviewDialog / ExportDialog 的 QDialog 布局约定。
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from photo_archiver.application.dtos import DuplicateReport

from photo_archiver.presentation.ui_text import (
    DUPLICATE_DIALOG_TITLE,
    DUPLICATE_GROUP_NODE,
    DUPLICATE_GROUP_PHOTOS,
    DUPLICATE_HEADER_LABELS,
    DUPLICATE_SUMMARY_FOUND,
    DUPLICATE_SUMMARY_NONE,
)


class DuplicateReportDialog(QDialog):
    """Display the duplicate detection report as a read-only tree.

    Each top-level node is one duplicate group (hash + member count);
    its children are the member photos with their original name and path.
    Closing the dialog is the only available action — no delete / archive
    buttons in the first version.
    """

    def __init__(
        self,
        report: "DuplicateReport",
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog with the duplicate report to display.

        Args:
            report: The ``DuplicateReport`` returned by DetectDuplicatesService.
                An empty report (``has_duplicates == False``) renders a friendly
                "no duplicates" placeholder so the user gets immediate feedback.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(DUPLICATE_DIALOG_TITLE)
        self.setMinimumSize(640, 480)
        self._report = report
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out the summary label, the duplicate tree, and the Close button."""
        layout = QVBoxLayout(self)

        summary = QLabel(self._summary_text())
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(list(DUPLICATE_HEADER_LABELS))
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._populate_tree()
        layout.addWidget(self._tree)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)  # type: ignore[attr-defined]
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _summary_text(self) -> str:
        """Return the human-readable summary line for the report header."""
        if not self._report.has_duplicates:
            return DUPLICATE_SUMMARY_NONE
        return DUPLICATE_SUMMARY_FOUND.format(
            group_count=self._report.group_count,
            photo_count=self._report.photos_in_groups,
        )

    def _populate_tree(self) -> None:
        """Fill the tree with one top-level node per duplicate group."""
        for group in self._report.groups:
            group_node = QTreeWidgetItem(
                [
                    DUPLICATE_GROUP_NODE.format(hash=group.content_hash[:12]),
                    DUPLICATE_GROUP_PHOTOS.format(count=len(group.members)),
                ]
            )
            for photo in group.members:
                member_node = QTreeWidgetItem(
                    group_node,
                    [
                        photo.original_name or photo.path.raw_path.name,
                        str(photo.path.raw_path),
                    ],
                )
                member_node.setForeground(1, Qt.GlobalColor.darkGray)  # type: ignore[attr-defined]
            self._tree.addTopLevelItem(group_node)
        self._tree.expandAll()
