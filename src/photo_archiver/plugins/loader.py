"""Plugin discovery and loading for Step 15 Plugin System.

Loads plugins from the ``examples/plugins/`` directory or from external paths
provided at runtime. Each plugin is a Python module that exports a ``plugin``
attribute conforming to the ``Plugin`` protocol.

Error handling: malformed/error plugins are logged and skipped; a single bad
plugin never crashes the host application (acceptance criterion 3).

阶段 1 加固（ADR-026，前置门拍板 2026-08-11）：

- Registry 启用两类生命周期分发——``ContextAwarePlugin``（``set_context → enable``）
  与无参 ``enable()``直调。签名识别走 ``hasattr(set_context)`` 探测而非
  "捕获 TypeError 重试"——插件内部真实 TypeError 不会被误判为兼容问题。
- 静默失败防护——启用后 ``actions()`` 返空且非声明式插件（走 Protocol 默认 noop）
  时日志 warning，提示可能误漏 ``enable`` 实现。

v2.0.0 收敛（ADR-030 兑现）：旧 ``enable(context)`` 兼容分发分支已移除——
Deprecated 承诺「保留一个版本」到期。持旧签名的外部插件将启用失败并进入
错误隔离（不启用该插件、记录 error，宿主续运行）。
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from photo_archiver.application.ports.plugin import Plugin
    from photo_archiver.application.ports.plugin_context import PluginContext


class PluginRegistry:
    """Holds all loaded plugins and manages their lifecycle."""

    def __init__(self, context: "PluginContext | None" = None) -> None:
        """Initialize an empty registry with an optional PluginContext.

        Args:
            context: PluginContext read-only facade injected into each plugin's
                enable(). Optional (None) so CI / unit tests can load plugins
                without a full Application bootstrap; v2 收敛拍板：可选注入。
        """
        self._context: "PluginContext | None" = context
        self._plugins: dict[str, Plugin] = {}
        self._enabled: set[str] = set()
        self._errors: list[tuple[str, str]] = []  # (plugin_name, error_message)

    # ── Registration ───────────────────────────────────────────────────────

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance directly without going through discovery.

        Public API for white-box tests and host-side wiring（review Minor-5 fix：
        替 ``registry._plugins[name] = plugin`` 私有访问）. Conflicts by name
        overwrite the previous registration — last write wins, matching the
        discovery path's behavior on re-loading a plugin module.

        Args:
            plugin: A Plugin-satisfying instance. Its ``name`` is used as the
                registry key.
        """
        self._plugins[plugin.name] = plugin  # type: ignore[index]  # UUID | None resolved by Protocol contract

    # ── Loading ──────────────────────────────────────────────────────────

    def load_from_path(self, path: Path) -> None:
        """Discover and load plugins from a single directory.

        Scans the directory for Python files (``.py``) and attempts to import
        each one. A valid plugin module must export a module-level ``plugin``
        variable that satisfies the ``Plugin`` protocol.

        Args:
            path: Directory to scan for plugin modules.
        """
        if not path.is_dir():
            logger.warning("Plugin directory not found: {}", path)
            return

        for module_path in sorted(path.iterdir()):
            if module_path.suffix != ".py" or module_path.name.startswith("_"):
                continue
            self._load_single(module_path)

    def load_all(self, *paths: Path) -> None:
        """Load plugins from one or more directories."""
        for path in paths:
            self.load_from_path(path)

    # ── Lifecycle ────────────────────────────────────────────────────────

    def enable_all(self) -> None:
        """Enable every loaded plugin via two-path dispatch.

        阶段 1 加固（ADR-026）；v2.0.0 收敛（ADR-030，旧兼容分支移除）：

        - ``ContextAwarePlugin``（``set_context`` 存）——``set_context(context) → enable()``。
        - 无参 ``enable()``——直调。
        - 静默失败防护——启用后 ``actions()`` 返空且非声明式时日志 warning。

        持旧 ``enable(context)`` 签名的插件不再受支持：调用即抛 TypeError 并落入
        错误隔离（该插件不启用、记 error、宿主续运行）。context 为 None 时
        （CI / 单测环境）两路均保降级可用。
        """
        for name, plugin in self._plugins.items():
            try:
                self._enable_plugin(name, plugin)
                self._enabled.add(name)
                logger.info("Plugin enabled: {}", name)
                self._warn_silent_failure(name, plugin)
            except Exception:
                logger.exception("Failed to enable plugin: {}", name)
                self._errors.append((name, "enable() raised an exception"))

    def _enable_plugin(self, name: str, plugin: "Plugin") -> None:
        """Dispatch enable via ContextAwarePlugin / plain no-arg enable.

        v2.0.0 收敛（ADR-030）：旧 ``enable(context)`` 分发分支已删除，无需
        ``inspect.signature`` 探测——无参调用直接下发。持旧签名的外部插件在此
        抛出 TypeError，由上层错误隔离捕获（该插件不启用，宿主续运行）。
        """
        if hasattr(plugin, "set_context"):
            # 新标准：set_context(context) → enable()
            if self._context is None:
                raise RuntimeError(
                    f"Plugin {name} requires ContextAwarePlugin path but context is None"
                )
            plugin.set_context(self._context)  # type: ignore[attr-defined]
            plugin.enable()  # type: ignore[call-arg]
            return

        # 无参：enable()
        plugin.enable()  # type: ignore[call-arg]

    def _warn_silent_failure(self, name: str, plugin: "Plugin") -> None:
        """Log warning if enabled plugin returns no actions and is non-declarative.

        防护兜底（ADR-026 MAJOR-1）：误漏 ``enable`` 实现（走 Protocol 默认 noop）
        后 ``actions()`` 返空且非声明式插件 → 日志 warning 提示可能误漏。
        ``ContextAwarePlugin(Plugin)`` 继承关系使此风险大幅降低——mypy 即报错，
        本防护属二道兜底。
        """
        try:
            actions = plugin.actions()
        except Exception:
            return  # actions() itself raising is separately logged elsewhere
        if not actions and not hasattr(plugin, "_context"):
            # 非声明式插件（无 set_context/_context 持）返空 actions——可能误漏 enable
            logger.warning(
                "Plugin {} enabled but actions() is empty — possible missed enable() override",
                name,
            )

    def disable_all(self) -> None:
        """Call ``disable()`` on every enabled plugin."""
        for name in list(self._enabled):
            plugin = self._plugins.get(name)
            if plugin is not None:
                try:
                    plugin.disable()
                except Exception:
                    logger.exception("Failed to disable plugin: {}", name)
            self._enabled.discard(name)

    # ── Query ────────────────────────────────────────────────────────────

    @property
    def plugins(self) -> dict[str, Plugin]:
        """Return name → Plugin mapping for all loaded plugins."""
        return dict(self._plugins)

    @property
    def enabled_plugins(self) -> dict[str, Plugin]:
        """Return name → Plugin mapping for currently enabled plugins."""
        return {n: p for n, p in self._plugins.items() if n in self._enabled}

    @property
    def errors(self) -> list[tuple[str, str]]:
        """Return list of (name, error) tuples from load/enable failures."""
        return list(self._errors)

    def has_errors(self) -> bool:
        """Return whether any load or enable errors were recorded."""
        return len(self._errors) > 0

    # ── Internal ─────────────────────────────────────────────────────────

    def _load_single(self, module_path: Path) -> None:
        """Attempt to import a single plugin module by its file path.

        The module must expose a ``plugin`` attribute conforming to ``Plugin``.
        Errors are logged but never propagated — a bad plugin is skipped.
        """
        module_name = module_path.stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(module_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load spec from {module_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.warning("Skipping plugin {}: {}", module_name, exc)
            self._errors.append((module_name, f"load failed: {exc}"))
            return

        raw = getattr(module, "plugin", None)
        if raw is None:
            msg = f"{module_name} has no 'plugin' attribute"
            logger.warning("Skipping plugin {}: {}", module_name, msg)
            self._errors.append((module_name, msg))
            return

        # Duck-type check: the object must have name, version, enable, disable
        # 阶段 1 加固（ADR-026 ISSUE-016 Minor-1 顺手修）：空 pass 改显式校验
        for attr in ("name", "version", "enable", "disable"):
            if attr in ("name", "version"):
                if not isinstance(getattr(raw, attr, None), str):
                    msg = f"{module_name}.plugin.{attr} is not a string property"
                    logger.warning("Skipping plugin {}: {}", module_name, msg)
                    self._errors.append((module_name, msg))
                    return
            else:
                if not callable(getattr(raw, attr, None)):
                    msg = f"{module_name}.plugin.{attr} is not callable"
                    logger.warning("Skipping plugin {}: {}", module_name, msg)
                    self._errors.append((module_name, msg))
                    return

        pname = raw.name if hasattr(raw, "name") else module_name
        if pname in self._plugins:
            msg = f"duplicate plugin name: {pname}"
            logger.warning("Skipping plugin {}: {}", module_name, msg)
            self._errors.append((module_name, msg))
            return

        self._plugins[pname] = raw  # type: ignore[assignment]
        logger.info("Plugin loaded: {} (v{}) from {}", pname, raw.version, module_path)
