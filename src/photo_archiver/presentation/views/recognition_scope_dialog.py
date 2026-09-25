"""Recognition scope dialog — 阶段 C Commit 3 的识别范围选择.

一次识别运行开始前的纯输入对话框，明确区分两个正交维度：

- **照片选择范围**：全部照片，或照片库当前多选中的照片（重新分析选中）。
- **人脸数量范围**：五档预设（[1] [2-3] [4-5] [6-10] [11+]）任意组合，
  每档对应一个领域 ``FaceCountRange``——范围判断发生在应用层
  （``classify_scope``），绝不下沉到 detector。

对话框只收集输入；默认全选五档（等价于"所有检出人脸的照片都在范围内"，
与 Commit 2 命令默认值 ``FaceCountRange(1, None)`` 同口径）。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import FaceCountRange
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_PRIMARY, assign_role

# 五档预设：[1] [2-3] [4-5] [6-10] [11+]（任务书范围 UI 的快捷生成器）。
_SCOPE_PRESETS: tuple[FaceCountRange, ...] = (
    FaceCountRange(1, 1),
    FaceCountRange(2, 3),
    FaceCountRange(4, 5),
    FaceCountRange(6, 10),
    FaceCountRange(11, None),
)


class RecognitionScopeDialog(QDialog):
    """Collect the photo scope and face-count ranges for one recognition run."""

    def __init__(
        self,
        selected_count: int = 0,
        parent: QWidget | None = None,
        retryable_count: int = 0,
        failure_service=None,
        latest_run_id=None,
    ) -> None:
        """Build the dialog; counts drive the photo-scope radio availability.

        ``retryable_count``（Stage F）：最近一次识别运行中未产出观测的照片数
        ——为 0 时「仅重试失败照片」不可选。``failure_service`` +
        ``latest_run_id`` 支撑「导出上次失败清单」只读入口。
        """
        super().__init__(parent)
        self.setWindowTitle(text.RECOGNITION_SCOPE_DIALOG_TITLE)
        self.setMinimumWidth(420)
        self._selected_count = selected_count
        self._retryable_count = retryable_count
        self._failure_service = failure_service
        self._latest_run_id = latest_run_id
        self._build_ui()

    def _build_ui(self) -> None:
        """Lay out the two scope groups, the hint and the ok/cancel row."""
        layout = QVBoxLayout(self)

        photo_group = QGroupBox(text.RECOGNITION_SCOPE_PHOTO_GROUP, self)
        photo_layout = QVBoxLayout(photo_group)
        self._all_photos_radio = QRadioButton(text.RECOGNITION_SCOPE_ALL_PHOTOS, photo_group)
        self._all_photos_radio.setChecked(True)
        photo_layout.addWidget(self._all_photos_radio)
        self._selected_photos_radio = QRadioButton(
            text.RECOGNITION_SCOPE_SELECTED_PHOTOS.format(count=self._selected_count),
            photo_group,
        )
        # 无选区时"仅选中照片"不可选——照片选择范围只能落在真实选区上。
        self._selected_photos_radio.setEnabled(self._selected_count > 0)
        photo_layout.addWidget(self._selected_photos_radio)
        self._retry_radio = QRadioButton(
            text.RECOGNITION_SCOPE_RETRY_PHOTOS.format(count=self._retryable_count),
            photo_group,
        )
        # Stage F：重试上次失败照片——无失败时不可选。
        self._retry_radio.setEnabled(self._retryable_count > 0)
        photo_layout.addWidget(self._retry_radio)
        layout.addWidget(photo_group)

        range_group = QGroupBox(text.RECOGNITION_SCOPE_RANGE_GROUP, self)
        range_layout = QHBoxLayout(range_group)
        self._range_checks: list[QCheckBox] = []
        for preset in _SCOPE_PRESETS:
            check = QCheckBox(f"[{preset}]", range_group)
            # 默认全选：与命令默认 FaceCountRange(1, None) 同口径，不做隐式过滤。
            check.setChecked(True)
            check.toggled.connect(self._update_ok_enabled)
            range_layout.addWidget(check)
            self._range_checks.append(check)
        layout.addWidget(range_group)

        hint = QLabel(text.RECOGNITION_SCOPE_RANGE_HINT, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._export_button = QPushButton(text.RECOGNITION_SCOPE_EXPORT_FAILURES, self)
        self._export_button.setEnabled(self._retryable_count > 0)
        self._export_button.clicked.connect(self._on_export_failures_clicked)
        layout.addWidget(self._export_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText(text.RECOGNITION_SCOPE_OK_BUTTON)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText(text.PEOPLE_PAGE_CANCEL_BUTTON)
        assign_role(self._ok_button, ROLE_PRIMARY)
        self._ok_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_ok_enabled()

    def _update_ok_enabled(self) -> None:
        """Keep OK disabled while no face-count range is selected."""
        self._ok_button.setEnabled(bool(self.selected_ranges))
        self._ok_button.setToolTip(
            "" if self.selected_ranges else text.RECOGNITION_SCOPE_AT_LEAST_ONE
        )

    @property
    def photo_scope_selected_only(self) -> bool:
        """Whether the run should cover only the library selection."""
        return self._selected_photos_radio.isChecked()

    @property
    def photo_scope(self) -> str:
        """Return the photo scope: "all" | "selected" | "retry"（Stage F）。"""
        if self._retry_radio.isChecked():
            return "retry"
        if self._selected_photos_radio.isChecked():
            return "selected"
        return "all"

    def _on_export_failures_clicked(self) -> None:
        """Stage F：导出上次失败清单（只读 CSV，不改业务状态）。"""
        if self._failure_service is None or self._latest_run_id is None:
            return
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        target, _ = QFileDialog.getSaveFileName(
            self, text.RECOGNITION_FAILURE_EXPORT_TITLE,
            "recognition_failures.csv", "CSV (*.csv)",
        )
        if not target:
            return
        rows = self._failure_service.export_csv(self._latest_run_id, target)
        QMessageBox.information(
            self, text.RECOGNITION_FAILURE_EXPORT_TITLE,
            text.RECOGNITION_FAILURE_EXPORT_DONE.format(count=rows, path=target),
        )

    @property
    def selected_ranges(self) -> tuple[FaceCountRange, ...]:
        """Return the checked face-count ranges in preset order (>= 1 entry on accept)."""
        return tuple(
            preset for preset, check in zip(_SCOPE_PRESETS, self._range_checks)
            if check.isChecked()
        )
