"""Plugin action result DTO — B5 v2 收敛版.

宿主渲染动作结果：Plugin.execute_action 改为返 ActionResult 结构化对象，
宿主负责渲染/展示；插件不直触 UI/文件系统（拍板裁决"宿主渲染动作结果"）。

三种结果态：
    Success: message + optional payload（如统计报表插件返计数 dict）
    Failure: message + error detail（插件捕获自身异常后返）
    NoOp: action_id 不属本插件 → 返 NoOp 让宿主续查下一个插件
"""

from dataclasses import dataclass
from typing import Any, Literal

ActionStatus = Literal["success", "failure", "noop"]


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Structured result a plugin returns from execute_action.

    The host renders this to the user; plugins never touch UI / filesystem
    directly (拍板 v2 收敛：宿主渲染动作结果).

    Attributes:
        status: One of "success" / "failure" / "noop"（Literal 静态守护 typo，
            review Minor-3 fix：替 str 让 mypy 核 MainWindow `_render_plugin_action_result`
            的 `result.status == "success"` 比对正确，typo 致 mypy 报错）。
        message: Human-readable summary the host surfaces to the user.
        payload: Optional structured data the host may render (e.g. a dict
            of counts for a stats report plugin). Untyped on purpose — the
            host decides rendering per payload shape.
    """

    status: ActionStatus
    message: str = ""
    payload: Any = None


def success(message: str, payload: Any = None) -> ActionResult:
    """Build a success ActionResult."""
    return ActionResult(status="success", message=message, payload=payload)


def failure(message: str, payload: Any = None) -> ActionResult:
    """Build a failure ActionResult."""
    return ActionResult(status="failure", message=message, payload=payload)


def noop() -> ActionResult:
    """Build a noop ActionResult — action_id not owned by this plugin."""
    return ActionResult(status="noop", message="")
