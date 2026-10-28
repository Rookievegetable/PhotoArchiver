"""ClusterRangeDialog tests — 聚类范围选择（任务书 D2）.

覆盖：默认仅 [1]（与历史口径一致）、OK 随选择联动、selected_ranges 按
预设顺序返回。
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialogButtonBox

from photo_archiver.domain import FaceCountRange
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.cluster_range_dialog import ClusterRangeDialog


def test_default_selection_is_single_face_only(qtbot):
    dialog = ClusterRangeDialog()
    qtbot.addWidget(dialog)

    assert dialog.selected_ranges == (FaceCountRange(1, 1),)
    ok = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled()
    assert ok.text() == text.CLUSTER_RANGE_OK_BUTTON


def test_ok_disabled_when_no_range_selected(qtbot):
    dialog = ClusterRangeDialog()
    qtbot.addWidget(dialog)
    for check in dialog._range_checks:
        check.setChecked(False)

    ok = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled() is False
    assert dialog._ok_button.toolTip() == text.CLUSTER_RANGE_AT_LEAST_ONE


def test_selected_ranges_follow_preset_order(qtbot):
    dialog = ClusterRangeDialog()
    qtbot.addWidget(dialog)
    # 勾选 [2-3] 与 [11+]：返回值按预设顺序而非勾选顺序。
    dialog._range_checks[1].setChecked(True)
    dialog._range_checks[4].setChecked(True)

    assert dialog.selected_ranges == (
        FaceCountRange(1, 1), FaceCountRange(2, 3), FaceCountRange(11, None),
    )
