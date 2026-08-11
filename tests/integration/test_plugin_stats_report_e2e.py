"""E2E test for stats_report_plugin end-to-end workflow（阶段 1，ADR-026）.

覆盖：
- 工具栏动作 → 插件 → Context → Result → 宿主报告对话框全链
- stats 插件只调 PluginContext.search_photos() + detect_duplicates()
- 输出项：照片总数 / pending/approved/rejected/none / 有/无拍摄日期 / 重复组/重复照片数量
- 返 ActionResult.success(..., PluginReport(...))——宿主 PluginReportDialog 渲染

用 fake PluginContext（不触真实 Application bootstrap）——本测试验插件端到端
动作链，非宿主装配链。
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from photo_archiver.application.dtos.plugin_action_result import ActionResult, PluginReport
from photo_archiver.application.dtos.plugin_context import (
    PluginDuplicateReport,
    PluginPhotoSummary,
)
from photo_archiver.application.ports.plugin_context import PluginContext

pytest.importorskip("PySide6")


def _make_fake_ctx_with_photos() -> "PluginContext":
    """Build a fake PluginContext returning canned photos for stats E2E."""

    class _FakeCtx:
        def search_photos(self, query):
            return (
                PluginPhotoSummary(
                    photo_id=UUID(int=1),
                    captured_at=datetime(2026, 1, 15),
                    registered_at=datetime.now(),
                    match_status="pending",
                ),
                PluginPhotoSummary(
                    photo_id=UUID(int=2),
                    captured_at=None,
                    registered_at=datetime.now(),
                    match_status="approved",
                ),
                PluginPhotoSummary(
                    photo_id=UUID(int=3),
                    captured_at=datetime(2026, 2, 20),
                    registered_at=datetime.now(),
                    match_status="none",
                ),
            )

        def detect_duplicates(self):
            return PluginDuplicateReport(
                groups=(),
                duplicate_group_count=0,
                duplicate_photo_count=0,
            )

    return _FakeCtx()  # type: ignore[return-value]


def test_stats_report_plugin_end_to_end_action_chain() -> None:
    """stats_report_plugin E2E：set_context → enable → execute → PluginReport.

    验输出项全列：Total / Pending / Approved / Rejected / None /
    With captured / Without captured / Duplicate groups / Photos in dup groups.
    """
    stats_path = (
        Path(__file__).resolve().parent.parent.parent
        / "examples"
        / "plugins"
        / "stats_report_plugin.py"
    )
    spec = importlib.util.spec_from_file_location("stats_plugin_test", str(stats_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stats = module.plugin

    # 新标准 ContextAwarePlugin：set_context → enable
    stats.set_context(_make_fake_ctx_with_photos())
    stats.enable()

    # 执行 stats.report 动作
    result = stats.execute_action("stats.report")
    assert isinstance(result, ActionResult)
    assert result.status == "success"
    assert result.report is not None
    assert isinstance(result.report, PluginReport)

    # 验输出项全列
    expected_metrics = {
        "Total photos",
        "Pending review",
        "Approved",
        "Rejected",
        "No recognition result",
        "With captured date",
        "Without captured date",
        "Duplicate groups",
        "Photos in duplicate groups",
    }
    actual_metrics = {row[0] for row in result.report.rows}
    assert actual_metrics == expected_metrics, f"Missing metrics: {expected_metrics - actual_metrics}"

    # 验数值正确（3 张照片：1 pending + 1 approved + 1 none，2 有 captured + 1 无）
    metrics_dict = {row[0]: row[1] for row in result.report.rows}
    assert metrics_dict["Total photos"] == 3
    assert metrics_dict["Pending review"] == 1
    assert metrics_dict["Approved"] == 1
    assert metrics_dict["Rejected"] == 0
    assert metrics_dict["No recognition result"] == 1
    assert metrics_dict["With captured date"] == 2
    assert metrics_dict["Without captured date"] == 1
    assert metrics_dict["Duplicate groups"] == 0
    assert metrics_dict["Photos in duplicate groups"] == 0


def test_stats_report_plugin_unknown_action_returns_noop() -> None:
    """stats_report_plugin 不属本插件的 action_id → noop."""
    stats_path = (
        Path(__file__).resolve().parent.parent.parent
        / "examples"
        / "plugins"
        / "stats_report_plugin.py"
    )
    spec = importlib.util.spec_from_file_location("stats_plugin_test2", str(stats_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stats = module.plugin

    stats.set_context(_make_fake_ctx_with_photos())
    stats.enable()

    result = stats.execute_action("unknown.action")
    assert result.status == "noop"
    assert result.report is None
