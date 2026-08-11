"""Plugin action result DTO — 阶段 1 公共边界加固（ADR-026）.

宿主渲染动作结果：Plugin.execute_action 返 ActionResult 结构化对象，宿主负责
渲染/展示；插件不直触 UI/文件系统（拍板裁决"宿主渲染动作结果"）。

三种结果态（ADR-026 收紧）：
    Success: message + optional PluginReport（结构化报表，宿主通用报告对话框渲染）
    Failure: message only（只带面向用户信息，不带任意对象）
    NoOp: action_id 不属本插件 → 返 NoOp 让宿主续查下一个插件

阶段 1 加固：``payload: Any`` 改为 ``report: PluginReport | None``——废止
``str(payload)`` 兜底渲染， PluginReport 单元格 ``str | int | float`` 混合
（宿主渲染层做格式化：数值列右对齐/排序/国际化数量格式）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActionStatus = Literal["success", "failure", "noop"]


@dataclass(frozen=True, slots=True)
class PluginReport:
    """Structured report a plugin returns via ``ActionResult.report``.

    宿主通用报告对话框渲染——title 标题、columns 列名、rows 二维数据。
    单元格 ``str | int | float`` 混合（ADR-026 裁决点 4=A）：插件给结构化
    数据，宿主渲染层做格式化（数值列右对齐/排序/国际化数量格式）。

    Attributes:
        title: Report dialog title (e.g. "Plugin: Stats Report").
        columns: Column header labels, one per row cell.
        rows: Each row is a tuple of cells aligned with ``columns`` by index.
            Cell types ``str | int | float``——宿主推断列类型做对齐/排序。
    """

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str | int | float, ...], ...]


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Structured result a plugin returns from execute_action.

    The host renders this to the user; plugins never touch UI / filesystem
    directly (拍板 v2 收敛：宿主渲染动作结果).

    Attributes:
        status: One of "success" / "failure" / "noop"（Literal 陙态守护 typo，
            review Minor-3 fix：替 str 让 mypy 核 MainWindow 渲染层
            ``result.status == "success"`` 比对正确，typo 致 mypy 报错）。
        message: Human-readable summary the host surfaces to the user.
        report: Optional structured PluginReport the host renders via
            通用报告对话框（ADR-026 收紧：替旧 ``payload: Any`` 兜底渲染）。
            ``success`` 可带 Report；``failure``/``noop`` 不带。
    """

    status: ActionStatus
    message: str = ""
    report: PluginReport | None = None


def success(message: str, report: PluginReport | None = None) -> ActionResult:
    """Build a success ActionResult with optional structured report.

    Args:
        message: Human-readable summary surfaced to the user.
        report: Optional PluginReport——宿主通用报告对话框渲染标题/列/行。
            无 report 时宿主走信息提示路径。
    """
    return ActionResult(status="success", message=message, report=report)


def failure(message: str) -> ActionResult:
    """Build a failure ActionResult——message only, no structured object.

    Args:
        message: Human-readable failure detail surfaced to the user via
            警告提示。不带任意对象（ADR-026 收紧：废止旧 ``payload`` 传错细节）。
    """
    return ActionResult(status="failure", message=message)


def noop() -> ActionResult:
    """Build a noop ActionResult — action_id not owned by this plugin."""
    return ActionResult(status="noop", message="")
