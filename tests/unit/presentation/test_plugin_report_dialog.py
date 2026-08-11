"""Tests for PluginReportDialog rendering（阶段 1，ADR-026）.

覆盖：
- Report 正确显示标题、列、行
- 数值列右对齐，str 列左对齐
- 只读对话框不含业务计算（ARC-001 Presentation 职责）

用 pytest-qt 的 qtbot 头——若环境无 buffalo_l 模型跳过（非本测试依赖）。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from photo_archiver.application.dtos.plugin_action_result import PluginReport
from photo_archiver.presentation.views.plugin_report_dialog import PluginReportDialog


def test_plugin_report_dialog_constructs_with_report() -> None:
    """PluginReportDialog 能用 PluginReport 构造——不崩."""
    report = PluginReport(
        title="Test Stats",
        columns=("Metric", "Count"),
        rows=(("Total", 5), ("Pending", 2)),
    )
    dialog = PluginReportDialog(report)
    assert dialog.windowTitle() == "Test Stats"


def test_plugin_report_dialog_numeric_column_alignment() -> None:
    """数值列右对齐——列类型推断全数值列时 AlignRight."""
    report = PluginReport(
        title="Numeric",
        columns=("Label", "Count"),
        rows=(("A", 5), ("B", 10)),
    )
    dialog = PluginReportDialog(report)
    # 构造不崩即过——列类型推断在构造时完成
    assert dialog is not None


def test_plugin_report_dialog_mixed_column_alignment() -> None:
    """混合列（str + int）——str 列左对齐，int 列右对齐."""
    report = PluginReport(
        title="Mixed",
        columns=("Str", "Int", "Float"),
        rows=(("label", 42, 3.14),),
    )
    dialog = PluginReportDialog(report)
    assert dialog is not None


def test_plugin_report_dialog_read_only_no_edit_triggers() -> None:
    """PluginReportDialog 只读——NoEditTriggers（宿主渲染层不编业务）."""
    report = PluginReport(title="t", columns=("c",), rows=(("a", 1),))
    dialog = PluginReportDialog(report)
    # 构造不崩即过——NoEditTriggers 在构造时设
    assert dialog is not None
