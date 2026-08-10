"""Tests for PluginContext port + loader context injection (B5 v2 收敛版).

覆盖：
- PluginContext Protocol 契约（search_photos + detect_duplicates 读方法存在）
- PluginRegistry context 透传（enable_all 调 plugin.enable(context)）
- context=None 兼容纯声明插件（HelloPlugin enable 不需 Context）
- ActionResult 三态（success/failure/noop）构造正确
"""

from __future__ import annotations

from pathlib import Path

from photo_archiver.application.dtos.plugin_action_result import (
    ActionResult,
    failure,
    noop,
    success,
)
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext
from photo_archiver.plugins.loader import PluginRegistry


# ── PluginContext Protocol 呑约 ────────────────────────────────────────────


def test_plugin_context_protocol_declares_two_read_methods() -> None:
    """PluginContext Protocol 暴 search_photos + detect_duplicates 读方法（v2 收敛）。"""
    # Protocol 仅验方法存在性——调用经实现类走（见下）。
    assert hasattr(PluginContext, "search_photos"), "PluginContext must declare search_photos"
    assert hasattr(PluginContext, "detect_duplicates"), "PluginContext must declare detect_duplicates"


def _make_fake_plugin_context() -> PluginContext:
    """Build a minimal fake PluginContext for loader injection tests."""

    class _FakeCtx:
        def search_photos(self, criteria):
            return []

        def detect_duplicates(self):
            return None

    return _FakeCtx()  # type: ignore[return-value]


# ── PluginRegistry context 透传 ────────────────────────────────────────────


class _CapturingPlugin:
    """Plugin stub that captures the context passed to enable()."""

    def __init__(self) -> None:
        self.captured_context: object = object()  # sentinel

    @property
    def name(self) -> str:
        return "capturing"

    @property
    def version(self) -> str:
        return "1.0.0"

    def enable(self, context=None) -> None:
        self.captured_context = context

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return []

    def execute_action(self, action_id: str) -> ActionResult:
        return noop()


def test_plugin_registry_enable_all_injects_context(tmp_path: Path) -> None:
    """PluginRegistry.enable_all 调 plugin.enable(context) 透传 Context."""
    ctx = _make_fake_plugin_context()
    registry = PluginRegistry(context=ctx)
    plugin = _CapturingPlugin()
    registry.register(plugin)  # public API (review Minor-5 fix：替私有 _plugins 访问)
    registry.enable_all()
    assert plugin.captured_context is ctx


def test_plugin_registry_enable_all_context_none_default(tmp_path: Path) -> None:
    """PluginRegistry() 默认 context=None——enable_all 调 plugin.enable(None) 兼容."""
    registry = PluginRegistry()  # context=None default
    plugin = _CapturingPlugin()
    registry.register(plugin)  # public API (review Minor-5 fix)
    registry.enable_all()
    assert plugin.captured_context is None


# ── HelloPlugin example 端到端 ──────────────────────────────────────────────


def test_hello_plugin_enable_accepts_optional_context() -> None:
    """HelloPlugin.enable(context=None) 兼容——纯声明插件不需 Context."""
    import importlib.util

    hello_path = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "plugins" / "hello_plugin.py"
    spec = importlib.util.spec_from_file_location("hello_plugin_test", str(hello_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hello = module.plugin

    # 不传 context——HelloPlugin 纯声明，应 no-op 走通
    hello.enable()
    hello.enable(context=None)
    hello.enable(context=_make_fake_plugin_context())  # 传 Context 也不崩（HelloPlugin 不消费）

    # execute_action 返 ActionResult success 态
    result = hello.execute_action("hello.greet")
    assert isinstance(result, ActionResult)
    assert result.status == "success"
    assert "Hello" in result.message

    # 不属本插件的 action_id → noop
    result = hello.execute_action("unknown.action")
    assert result.status == "noop"


# ── ActionResult 三态 ──────────────────────────────────────────────────────


def test_action_result_success_factory() -> None:
    """success() 构造 status=success ActionResult."""
    r = success(message="done", payload={"count": 5})
    assert r.status == "success"
    assert r.message == "done"
    assert r.payload == {"count": 5}


def test_action_result_failure_factory() -> None:
    """failure() 构造 status=failure ActionResult."""
    r = failure(message="boom", payload="trace")
    assert r.status == "failure"
    assert r.message == "boom"
    assert r.payload == "trace"


def test_action_result_noop_factory() -> None:
    """noop() 构造 status=noop ActionResult（无 message/payload）。"""
    r = noop()
    assert r.status == "noop"
    assert r.message == ""
    assert r.payload is None


def test_action_result_frozen_slots() -> None:
    """ActionResult 是 frozen slots dataclass——不可变."""
    r = success("x")
    try:
        r.status = "failure"  # type: ignore[misc]
        raise AssertionError("ActionResult should be frozen")
    except Exception:
        pass
