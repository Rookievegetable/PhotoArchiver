"""Tests for PluginContext port + loader context injection（阶段 1，ADR-026）.

覆盖：
- PluginContext Protocol 契约（search_photos + detect_duplicates 读方法存在，返 Plugin DTO）
- ContextAwarePlugin Protocol 契约（set_context + enable + disable + actions + execute_action）
- PluginRegistry 两类生命周期分发（ContextAwarePlugin / 无参 enable）
- context=None 测试环境保降级可用
- ActionResult 三态（success/failure/noop）+ PluginReport 构造正确
- 静默失败防护（误漏 enable 实现 actions() 返空时 warning）

阶段 1 加固（ADR-026）：测试改新 API——``set_context → enable``、
``search_photos(PluginPhotoQuery) → tuple[PluginPhotoSummary, ...]``、
``ActionResult.report: PluginReport | None``。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from photo_archiver.application.dtos.plugin_action_result import (
    ActionResult,
    PluginReport,
    failure,
    noop,
    success,
)
from photo_archiver.application.dtos.plugin_context import (
    PluginDuplicateReport,
    PluginPhotoQuery,
    PluginPhotoSummary,
)
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext
from photo_archiver.plugins.loader import PluginRegistry


# ── PluginContext Protocol 契约 ────────────────────────────────────────────


def test_plugin_context_protocol_declares_two_read_methods() -> None:
    """PluginContext Protocol 暴 search_photos + detect_duplicates 读方法."""
    assert hasattr(PluginContext, "search_photos"), "PluginContext must declare search_photos"
    assert hasattr(PluginContext, "detect_duplicates"), "PluginContext must declare detect_duplicates"


def _make_fake_plugin_context() -> PluginContext:
    """Build a minimal fake PluginContext for loader injection tests (阶段 1 新 API)."""

    class _FakeCtx:
        def search_photos(self, query: PluginPhotoQuery) -> tuple[PluginPhotoSummary, ...]:
            return ()

        def detect_duplicates(self) -> PluginDuplicateReport:
            return PluginDuplicateReport(
                groups=(),
                duplicate_group_count=0,
                duplicate_photo_count=0,
            )

    return _FakeCtx()  # type: ignore[return-value]


# ── ContextAwarePlugin Protocol 契约 ──────────────────────────────────────


def test_context_aware_plugin_protocol_declares_set_context() -> None:
    """ContextAwarePlugin Protocol 暴 set_context 方法（ADR-026 新标准）."""
    from photo_archiver.application.ports.plugin import ContextAwarePlugin

    assert hasattr(ContextAwarePlugin, "set_context"), "ContextAwarePlugin must declare set_context"
    assert hasattr(ContextAwarePlugin, "enable"), "ContextAwarePlugin must inherit enable from Plugin"


# ── PluginRegistry 两类生命周期分发 ────────────────────────────────────────


class _ContextAwareStub:
    """ContextAwarePlugin standard stub — set_context → enable."""

    def __init__(self) -> None:
        self.captured_context: object = object()  # sentinel
        self.enable_called: bool = False

    @property
    def name(self) -> str:
        return "context_aware"

    @property
    def version(self) -> str:
        return "1.0.0"

    def set_context(self, context: PluginContext) -> None:
        self.captured_context = context

    def enable(self) -> None:
        self.enable_called = True

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return [PluginAction(id="stub.run", label="Stub")]

    def execute_action(self, action_id: str) -> ActionResult:
        return noop()


class _PlainEnableStub:
    """旧无参 enable() stub."""

    @property
    def name(self) -> str:
        return "plain"

    @property
    def version(self) -> str:
        return "1.0.0"

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return [PluginAction(id="plain.run", label="Plain")]

    def execute_action(self, action_id: str) -> ActionResult:
        return noop()


def test_registry_enable_context_aware_plugin_via_set_context_then_enable() -> None:
    """ContextAwarePlugin 路径：set_context(context) → enable()（ADR-026 新标准）."""
    ctx = _make_fake_plugin_context()
    registry = PluginRegistry(context=ctx)
    plugin = _ContextAwareStub()
    registry.register(plugin)
    registry.enable_all()
    assert plugin.captured_context is ctx, "set_context must receive the registry context"
    assert plugin.enable_called, "enable() must be called after set_context"


def test_registry_enable_plain_enable_no_args() -> None:
    """旧无参 enable() 路径——直调无参."""
    ctx = _make_fake_plugin_context()
    registry = PluginRegistry(context=ctx)
    plugin = _PlainEnableStub()
    registry.register(plugin)
    registry.enable_all()  # 不崩即过——plain enable() 不收 context


def test_registry_context_none_context_aware_plugin_raises() -> None:
    """context=None 时 ContextAwarePlugin 路径不可用——报错并跳过该插件."""
    registry = PluginRegistry()  # context=None default
    plugin = _ContextAwareStub()
    registry.register(plugin)
    registry.enable_all()
    # 错误隔离：plugin 未启用，registry.has_errors() 真
    assert plugin.name not in registry.enabled_plugins
    assert registry.has_errors()


def test_registry_context_none_plain_enable_works() -> None:
    """context=None 时旧无参 enable() 路径可用."""
    registry = PluginRegistry()  # context=None default
    plugin = _PlainEnableStub()
    registry.register(plugin)
    registry.enable_all()
    assert plugin.name in registry.enabled_plugins


# ── HelloPlugin example 端到端 ──────────────────────────────────────────────


def test_hello_plugin_context_aware_standard_end_to_end() -> None:
    """HelloPlugin 演示 ContextAwarePlugin 新标准——set_context → enable → actions → execute."""
    hello_path = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "plugins" / "hello_plugin.py"
    spec = importlib.util.spec_from_file_location("hello_plugin_test", str(hello_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hello = module.plugin

    # 新标准：set_context → enable（context 接收但不消费——HelloPlugin 纯声明）
    hello.set_context(_make_fake_plugin_context())
    hello.enable()

    # execute_action 返 ActionResult success 态
    result = hello.execute_action("hello.greet")
    assert isinstance(result, ActionResult)
    assert result.status == "success"
    assert "Hello" in result.message
    assert result.report is None, "HelloPlugin success 不带 PluginReport"

    # 不属本插件的 action_id → noop
    result = hello.execute_action("unknown.action")
    assert result.status == "noop"


# ── ActionResult 三态 + PluginReport（ADR-026 收紧）────────────────────────


def test_action_result_success_factory_with_report() -> None:
    """success() 可带 PluginReport——宿主通用报告对话框渲染."""
    report = PluginReport(title="Stats", columns=("Metric",), rows=(("Total", 5),))
    r = success(message="done", report=report)
    assert r.status == "success"
    assert r.message == "done"
    assert r.report is report
    assert r.report.title == "Stats"


def test_action_result_success_factory_no_report() -> None:
    """success() 无 report——宿主信息提示路径."""
    r = success(message="ok")
    assert r.status == "success"
    assert r.report is None


def test_action_result_failure_factory_no_payload() -> None:
    """failure() 只带 message——不带任意对象（ADR-026 收紧：废止旧 payload）."""
    r = failure(message="boom")
    assert r.status == "failure"
    assert r.message == "boom"
    assert r.report is None, "failure 不带 PluginReport"


def test_action_result_noop_factory() -> None:
    """noop() 不带内容——action_id 不属本插件."""
    r = noop()
    assert r.status == "noop"
    assert r.message == ""
    assert r.report is None


def test_action_result_frozen_slots() -> None:
    """ActionResult 是 frozen slots dataclass——不可变."""
    r = success("x")
    with pytest.raises(Exception):
        r.status = "failure"  # type: ignore[misc]


def test_plugin_report_frozen_slots() -> None:
    """PluginReport 是 frozen slots dataclass——不可变."""
    report = PluginReport(title="t", columns=("c",), rows=(("a", 1),))
    with pytest.raises(Exception):
        report.title = "other"  # type: ignore[misc]


def test_plugin_report_cell_types_mixed_str_int_float() -> None:
    """PluginReport 单元格 str | int | float 混合（ADR-026 裁决点 4=A）."""
    report = PluginReport(
        title="mixed",
        columns=("Str", "Int", "Float"),
        rows=(("label", 42, 3.14),),
    )
    assert report.rows[0][0] == "label"
    assert report.rows[0][1] == 42
    assert report.rows[0][2] == 3.14


# ── Plugin DTO 不可变 + Literal 值域 ───────────────────────────────────────


def test_plugin_photo_query_frozen_slots() -> None:
    """PluginPhotoQuery 是 frozen slots——不可变."""
    query = PluginPhotoQuery()
    with pytest.raises(Exception):
        query.person_id = None  # type: ignore[misc]


def test_plugin_photo_summary_frozen_slots() -> None:
    """PluginPhotoSummary 是 frozen slots——不可变."""
    from datetime import datetime
    from uuid import UUID

    summary = PluginPhotoSummary(
        photo_id=UUID(int=1),
        captured_at=None,
        registered_at=datetime.now(),
        match_status="none",
    )
    with pytest.raises(Exception):
        summary.match_status = "approved"  # type: ignore[misc]


def test_plugin_duplicate_report_frozen_slots() -> None:
    """PluginDuplicateReport 是 frozen slots——不可变."""
    report = PluginDuplicateReport(
        groups=(),
        duplicate_group_count=0,
        duplicate_photo_count=0,
    )
    with pytest.raises(Exception):
        report.duplicate_group_count = 5  # type: ignore[misc]
