"""Stats Report Plugin — 阶段 1 端到端验收插件（ADR-026）.

只调 ``PluginContext.search_photos()`` + ``detect_duplicates()`` 两个读方法，
产照片统计报表返 ``ActionResult.success(..., PluginReport(...))``——宿主
PluginReportDialog 渲染。

输出项（ADR-026 §6）：
    - 照片总数
    - pending / approved / rejected / none 数量
    - 有拍摄日期 / 无拍摄日期数量
    - 重复组数量
    - 重复照片数量

按 MAJOR-2 裁决点 3=A：``PluginPhotoQuery.match_status`` 不含 none（3 态），
取 none 数量需 ``search_photos(PluginPhotoQuery())`` 取全集后客户端过滤
``match_status == "none"``。
"""

from __future__ import annotations

from photo_archiver.application.dtos.plugin_action_result import ActionResult, PluginReport, success
from photo_archiver.application.dtos.plugin_context import PluginPhotoQuery
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext


class StatsReportPlugin:
    """Stats report plugin — 阶段 1 端到端验收插件（ContextAwarePlugin 标准）."""

    @property
    def name(self) -> str:
        """Return the stable display name."""
        return "stats_report"

    @property
    def version(self) -> str:
        """Return the plugin version."""
        return "1.0.0"

    def set_context(self, context: PluginContext) -> None:
        """Store the host-provided read-only PluginContext for execute_action."""
        self._context: PluginContext = context

    def enable(self) -> None:
        """No-op activation——资源在 set_context 已注入."""

    def disable(self) -> None:
        """No-op deactivation."""

    def actions(self) -> list[PluginAction]:
        """Register one 'Stats Report' menu action."""
        return [
            PluginAction(
                id="stats.report",
                label="Stats Report",
                tooltip="Show photo statistics from the loaded library",
            ),
        ]

    def execute_action(self, action_id: str) -> ActionResult:
        """Execute the requested action, returning a structured PluginReport.

        按 ADR-026 §6 输出项：照片总数 / pending/approved/rejected/none 数量 /
        有/无拍摄日期数量 / 重复组数量 / 重复照片数量。
        """
        if action_id != "stats.report":
            from photo_archiver.application.dtos.plugin_action_result import noop

            return noop()

        photos = self._context.search_photos(PluginPhotoQuery())
        duplicates = self._context.detect_duplicates()

        total = len(photos)
        pending = sum(1 for p in photos if p.match_status == "pending")
        approved = sum(1 for p in photos if p.match_status == "approved")
        rejected = sum(1 for p in photos if p.match_status == "rejected")
        none_status = sum(1 for p in photos if p.match_status == "none")
        has_captured = sum(1 for p in photos if p.captured_at is not None)
        no_captured = total - has_captured

        report = PluginReport(
            title="Photo Library Stats",
            columns=("Metric", "Count"),
            rows=(
                ("Total photos", total),
                ("Pending review", pending),
                ("Approved", approved),
                ("Rejected", rejected),
                ("No recognition result", none_status),
                ("With captured date", has_captured),
                ("Without captured date", no_captured),
                ("Duplicate groups", duplicates.duplicate_group_count),
                ("Photos in duplicate groups", duplicates.duplicate_photo_count),
            ),
        )
        return success(message="Stats report generated.", report=report)


# Module-level export the loader discovers.
plugin = StatsReportPlugin()
