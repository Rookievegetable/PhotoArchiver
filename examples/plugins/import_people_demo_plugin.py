"""Import People Demo Plugin — 阶段 3 端到端验收插件（ADR-028）.

只调 ``PluginContext.import_people()`` 写方法，从插件内置样例行导入人员实体，
返 ``ActionResult.success(..., PluginReport(...))`` 摘要（imported/skipped/
errors 明细）——宿主 PluginReportDialog 渲染。

按 ADR-028 拍板：

- 裁决点 1=A 仅 import_people 先行（export 续暂缓留后续轮单独裁决）。
- 裁决点 2=A 无宿主审批门（插件直调 Service，宿主仅渲染 ActionResult）。
- 裁决点 3=C 双向 DTO 脱 Domain——入参/结果均 Plugin DTO，
  ``imported_person_ids`` 为 ``tuple[str, ...]`` 非 UUID。

样例行均携带 identity（其中一条与首条重复，用于演示 skipped 计数）——带
identity 的行重复执行只会计入 skipped，因此本插件重复执行是幂等的、不会产生
重复人员；注意无 identity 的行不做去重，每次执行都会重新导入。
"""

from __future__ import annotations

from photo_archiver.application.dtos.plugin_action_result import ActionResult, PluginReport, success
from photo_archiver.application.dtos.plugin_context import (
    PluginImportPeopleCommand,
    PluginImportPersonRow,
)
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext


class ImportPeopleDemoPlugin:
    """Import people demo plugin — 阶段 3 端到端验收插件（ContextAware 标准）."""

    # 内置样例行：两条可导入 + 一条重复身份（演示 skipped 计数）。全部携带
    # identity——去重仅作用于带 identity 的行（见 ImportPeopleService.import_rows），
    # 全量带身份保证重复执行本动作时整批幂等。
    _DEMO_ROWS = (
        PluginImportPersonRow(name="张三", identity="DEMO-001", department="Demo Dept"),
        PluginImportPersonRow(name="李四", identity="DEMO-002", department="Demo Dept"),
        PluginImportPersonRow(name="张三-重复", identity="DEMO-001"),
    )

    @property
    def name(self) -> str:
        """Return the stable display name."""
        return "import_people_demo"

    @property
    def version(self) -> str:
        """Return the plugin version."""
        return "1.0.0"

    def set_context(self, context: PluginContext) -> None:
        """Store the host-provided PluginContext for execute_action."""
        self._context: PluginContext = context

    def enable(self) -> None:
        """No-op activation——上下文在 set_context 已注入."""

    def disable(self) -> None:
        """No-op deactivation."""

    def actions(self) -> list[PluginAction]:
        """Register one 'Import People (Demo)' menu action."""
        return [
            PluginAction(
                id="people.import_demo",
                label="Import People (Demo)",
                tooltip="Import demo people rows through PluginContext.import_people",
            ),
        ]

    def execute_action(self, action_id: str) -> ActionResult:
        """Execute the demo import and return a structured summary report."""
        if action_id != "people.import_demo":
            from photo_archiver.application.dtos.plugin_action_result import noop

            return noop()

        result = self._context.import_people(PluginImportPeopleCommand(rows=self._DEMO_ROWS))

        detail_rows: tuple[tuple[str | int | float, ...], ...] = (
            ("Imported", result.imported_count),
            ("Skipped (duplicate identity)", result.skipped_count),
            ("Error count", len(result.errors)),
        ) + tuple(
            (f"Error {index + 1}", error)
            for index, error in enumerate(result.errors)
        )
        report = PluginReport(
            title="Import People (Demo)",
            columns=("Metric", "Value"),
            rows=detail_rows,
        )
        message = (
            f"Imported {result.imported_count}, "
            f"skipped {result.skipped_count}, "
            f"errors {len(result.errors)}."
        )
        return success(message=message, report=report)


# Module-level export the loader discovers.
plugin = ImportPeopleDemoPlugin()