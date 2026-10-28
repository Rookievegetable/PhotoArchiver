"""聚类范围选择对话框（任务书 §3 A3/D2）.

运行人脸聚类前的纯输入对话框：五档人脸数量预设（[1] [2-3] [4-5] [6-10]
[11+]）任意组合，每档对应一个领域 ``FaceCountRange``——范围判断发生在应用
层（``classify_scope``），绝不下沉到聚类算法。

默认仅 [1] 选中（任务书 D2 裁决：与历史口径一致，防重聚类漂移；合影不
参与聚类但保留全部检测记录）。"记住上次选择"为 backlog（任务书 §7）。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import FaceCountRange
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.visual_style import ROLE_PRIMARY, assign_role

# 五档预设：与退役的识别范围对话框同口径（任务书 D2 复用）。
_CLUSTER_RANGE_PRESETS: tuple[FaceCountRange, ...] = (
    FaceCountRange(1, 1),
    FaceCountRange(2, 3),
    FaceCountRange(4, 5),
    FaceCountRange(6, 10),
    FaceCountRange(11, None),
)


class ClusterRangeDialog(QDialog):
    """Collect the face-count ranges for one clustering execution."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the range checklist; OK stays disabled while nothing selected."""
        super().__init__(parent)
        self.setWindowTitle(text.CLUSTER_RANGE_DIALOG_TITLE)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        range_group = QGroupBox(text.CLUSTER_RANGE_GROUP, self)
        range_layout = QHBoxLayout(range_group)
        self._range_checks: list[QCheckBox] = []
        for preset in _CLUSTER_RANGE_PRESETS:
            check = QCheckBox(f"[{preset}]", range_group)
            # D2：默认仅 [1]——单脸照片与名单顺序配对口径一致。
            check.setChecked(preset == FaceCountRange(1, 1))
            check.toggled.connect(self._update_ok_enabled)
            range_layout.addWidget(check)
            self._range_checks.append(check)
        layout.addWidget(range_group)

        hint = QLabel(text.CLUSTER_RANGE_HINT, self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText(text.CLUSTER_RANGE_OK_BUTTON)
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
            "" if self.selected_ranges else text.CLUSTER_RANGE_AT_LEAST_ONE
        )

    @property
    def selected_ranges(self) -> tuple[FaceCountRange, ...]:
        """Return the checked face-count ranges in preset order (>= 1 on accept)."""
        return tuple(
            preset
            for preset, check in zip(_CLUSTER_RANGE_PRESETS, self._range_checks)
            if check.isChecked()
        )
