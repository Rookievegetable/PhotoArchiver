"""Plugin report dialog — 通用只读报告对话框（阶段 1，ADR-026）.

宿主渲染插件返 PluginReport 的通用对话框——只做渲染，不含业务计算。
QTableWidget 表格渲染 title/columns/rows；单元格 ``str | int | float``
混合（ADR-026 裁决点 4=A）：宿主推断列类型做对齐——数值列右对齐，str 列左对齐。

复刻既有 ``ArchivePreviewDialog`` / ``DuplicateReportDialog`` 的 QDialog 布局约定。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from photo_archiver.application.dtos.plugin_action_result import PluginReport


class PluginReportDialog(QDialog):
    """Read-only dialog rendering a PluginReport as a table.

    宿主渲染层职责（ARC-001 Presentation）：只做展示，不含业务计算。
    列类型推断——全数值列右对齐，含 str 列左对齐。
    """

    def __init__(self, report: PluginReport, parent: object | None = None) -> None:
        """Initialize the dialog with the report to render.

        Args:
            report: PluginReport 持 title/columns/rows——单元格 str | int | float 混合。
            parent: Optional parent widget.
        """
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle(report.title)
        self.setModal(True)

        layout = QVBoxLayout(self)

        title_label = QLabel(report.title, self)
        layout.addWidget(title_label)

        table = QTableWidget(len(report.rows), len(report.columns), self)
        table.setHorizontalHeaderLabels(list(report.columns))
        table.setEditTriggers(QTableWidget.NoEditTriggers)  # type: ignore[attr-defined]
        table.verticalHeader().setVisible(False)

        # 列类型推断：全数值列右对齐
        numeric_columns: set[int] = set()
        for col_idx in range(len(report.columns)):
            all_numeric = True
            for row in report.rows:
                if col_idx >= len(row):
                    all_numeric = False
                    break
                cell = row[col_idx]
                if not isinstance(cell, (int, float)):
                    all_numeric = False
                    break
            if all_numeric and len(report.rows) > 0:
                numeric_columns.add(col_idx)

        for row_idx, row in enumerate(report.rows):
            for col_idx, cell in enumerate(row):
                item = QTableWidgetItem(str(cell))
                if col_idx in numeric_columns:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)

        table.resizeColumnsToContents()
        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)  # type: ignore[attr-defined, call-arg]
        buttons.rejected.connect(self.reject)  # type: ignore[attr-defined]
        buttons.accepted.connect(self.accept)  # type: ignore[attr-defined]
        layout.addWidget(buttons)
