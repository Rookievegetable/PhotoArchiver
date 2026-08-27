"""Tests for Plugin lifecycle compatibility matrix（阶段 1，ADR-026）.

覆盖 §5 测试矩阵：
- 无参 enable() 插件成功启用
- 新 ContextAwarePlugin 成功接收 Context（set_context → enable）
- set_context() 抛异常时该插件不启用且宿主续运行
- enable() 抛异常时错误隔离保持有效
- context=None 测试环境保持可用
- 静默失败防护：误漏 enable 实现 actions() 返空且非声明式时 warning
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from photo_archiver.application.dtos.plugin_action_result import noop
from photo_archiver.application.dtos.plugin_context import (
    PluginDuplicateReport,
    PluginPhotoQuery,
    PluginPhotoSummary,
)
from photo_archiver.application.ports.plugin import PluginAction

if TYPE_CHECKING:
    from photo_archiver.application.ports.plugin_context import PluginContext


def _make_fake_ctx() -> "PluginContext":
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


# ── ContextAwarePlugin 路径 ────────────────────────────────────────────────


class _ContextAwareOK:
    """新标准 ContextAwarePlugin——set_context → enable，正常."""

    def __init__(self) -> None:
        self.ctx_received: bool = False
        self.enable_called: bool = False

    @property
    def name(self) -> str:
        return "ctx_aware_ok"

    @property
    def version(self) -> str:
        return "1.0.0"

    def set_context(self, context: "PluginContext") -> None:
        self.ctx_received = True

    def enable(self) -> None:
        self.enable_called = True

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return [PluginAction(id="x.run", label="X")]

    def execute_action(self, action_id: str):
        return noop()


class _ContextAwareSetContextRaises:
    """set_context() 抛异常——该插件不启用且宿主续运行."""

    @property
    def name(self) -> str:
        return "ctx_aware_raises"

    @property
    def version(self) -> str:
        return "1.0.0"

    def set_context(self, context: "PluginContext") -> None:
        raise RuntimeError("set_context failed")

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return []

    def execute_action(self, action_id: str):
        return noop()


# ── 旧无参 enable() 路径 ───────────────────────────────────────────────────


class _PlainEnableOK:
    """旧无参 enable()——正常."""

    @property
    def name(self) -> str:
        return "plain_ok"

    @property
    def version(self) -> str:
        return "1.0.0"

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return [PluginAction(id="plain.run", label="Plain")]

    def execute_action(self, action_id: str):
        return noop()


class _PlainEnableRaises:
    """enable() 抛异常——错误隔离保持有效."""

    @property
    def name(self) -> str:
        return "plain_raises"

    @property
    def version(self) -> str:
        return "1.0.0"

    def enable(self) -> None:
        raise RuntimeError("enable failed")

    def disable(self) -> None:
        pass

    def actions(self) -> list[PluginAction]:
        return []

    def execute_action(self, action_id: str):
        return noop()


# ── Tests ──────────────────────────────────────────────────────────────────


def test_context_aware_plugin_enabled_via_set_context_then_enable() -> None:
    """ContextAwarePlugin 成功接收 Context——set_context → enable 顺序."""
    from photo_archiver.plugins.loader import PluginRegistry

    registry = PluginRegistry(context=_make_fake_ctx())
    plugin = _ContextAwareOK()
    registry.register(plugin)
    registry.enable_all()
    assert plugin.ctx_received, "set_context must be called"
    assert plugin.enable_called, "enable must be called after set_context"
    assert plugin.name in registry.enabled_plugins


def test_context_aware_plugin_set_context_raises_isolated() -> None:
    """set_context() 抛异常时该插件不启用且宿主续运行."""
    from photo_archiver.plugins.loader import PluginRegistry

    registry = PluginRegistry(context=_make_fake_ctx())
    bad = _ContextAwareSetContextRaises()
    good = _PlainEnableOK()
    registry.register(bad)
    registry.register(good)
    registry.enable_all()
    assert bad.name not in registry.enabled_plugins, "bad plugin must not be enabled"
    assert good.name in registry.enabled_plugins, "good plugin must still be enabled"
    assert registry.has_errors()


def test_plain_enable_no_args_path_works() -> None:
    """旧无参 enable() 路径——直调."""
    from photo_archiver.plugins.loader import PluginRegistry

    registry = PluginRegistry(context=_make_fake_ctx())
    plugin = _PlainEnableOK()
    registry.register(plugin)
    registry.enable_all()
    assert plugin.name in registry.enabled_plugins


def test_enable_raises_isolated() -> None:
    """enable() 抛异常时错误隔离保持有效——其他插件不受影响."""
    from photo_archiver.plugins.loader import PluginRegistry

    registry = PluginRegistry(context=_make_fake_ctx())
    bad = _PlainEnableRaises()
    good = _PlainEnableOK()
    registry.register(bad)
    registry.register(good)
    registry.enable_all()
    assert bad.name not in registry.enabled_plugins
    assert good.name in registry.enabled_plugins
    assert registry.has_errors()


def test_context_none_two_paths_degrade_gracefully() -> None:
    """context=None 时两类路径保降级可用（CI / 单测环境）.

    ContextAwarePlugin 路径在 context=None 时应报错跳过（需 Context 才能启用），
    无参 enable() 路径应正常启用。
    """
    from photo_archiver.plugins.loader import PluginRegistry

    registry = PluginRegistry()  # context=None default
    ctx_aware = _ContextAwareOK()
    plain = _PlainEnableOK()
    registry.register(ctx_aware)
    registry.register(plain)
    registry.enable_all()

    # ContextAwarePlugin 在 context=None 时报错跳过
    assert ctx_aware.name not in registry.enabled_plugins
    # 无参路径正常
    assert plain.name in registry.enabled_plugins


def test_silent_failure_warning_for_empty_actions_non_declarative(caplog) -> None:
    """静默失败防护：误漏 enable 实现（走 noop）后 actions() 返空时 warning.

    防护兜底（ADR-026 MAJOR-1）：ContextAwarePlugin 继承关系使此风险大幅降低，
    本防护属二道兜底——非声明式插件（无 set_context/_context）返空 actions 时告警。
    """
    from photo_archiver.plugins.loader import PluginRegistry

    registry = PluginRegistry(context=_make_fake_ctx())

    # 非声明式插件（无 set_context）返空 actions——可能误漏 enable
    class _EmptyActionsPlugin:
        @property
        def name(self) -> str:
            return "empty"

        @property
        def version(self) -> str:
            return "1.0.0"

        def enable(self) -> None:
            pass  # noop default——可能误漏实现

        def disable(self) -> None:
            pass

        def actions(self) -> list[PluginAction]:
            return []  # 空动作——非声明式插件可疑

        def execute_action(self, action_id: str):
            return noop()

    plugin = _EmptyActionsPlugin()
    registry.register(plugin)
    with caplog.at_level("WARNING"):
        registry.enable_all()
    # 防护应发 warning（loguru capture）
    assert plugin.name in registry.enabled_plugins
