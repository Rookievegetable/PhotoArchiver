"""Plugin port protocol for Step 15 Plugin System.

Defines the ``Plugin`` and ``ContextAwarePlugin`` interfaces that all plugins
must implement. The interface lives in the Application layer port boundary so
that plugins (which may reside in external packages) depend only on Application
public API, never on Infrastructure internals (DEP-060/061/062).

The Application and Presentation layers consume plugins through this protocol
without importing concrete plugin classes — core code never depends on any
specific plugin (acceptance criterion 1).

阶段 1 加固（ADR-026，前置门拍板 2026-08-11）：

- ``Plugin.enable()`` 改无参——生命周期与上下文注入解耦，``context`` 不再
  混入 ``enable`` 签名。旧 ``enable(context)`` 签名作兼容路径 Deprecated
  保留一个版本（Registry 用 ``inspect.signature`` 识别兼容，详见
  ``plugins/loader.py``）。
- 新增 ``ContextAwarePlugin(Plugin)``——继承 Plugin，多一个
  ``set_context(context)`` 方法。新标准插件须同时实现 ``set_context +
  enable + disable + actions + execute_action``，mypy 静态守护完整。
  Registry 启用顺序：``set_context(context) → enable()``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from photo_archiver.application.dtos.plugin_action_result import ActionResult
    from photo_archiver.application.ports.plugin_context import PluginContext


class PluginAction:
    """Describes a single menu item or toolbar action a plugin registers.

    The host application reads the list of actions from ``Plugin.actions()``
    after loading and creates the corresponding UI elements.
    """

    def __init__(
        self,
        id: str,
        label: str,
        tooltip: str = "",
        icon_name: str = "",
    ) -> None:
        """Initialize a plugin action descriptor.

        Args:
            id: Stable identifier for the action (e.g. ``"hello_plugin.greet"``).
            label: Human-readable menu label (e.g. ``"Greet"``).
            tooltip: Status-bar / tooltip text.
            icon_name: Optional icon resource name.
        """
        self.id = id
        self.label = label
        self.tooltip = tooltip
        self.icon_name = icon_name


class Plugin(Protocol):
    """The interface every plugin must satisfy.

    All methods have default implementations so a minimal plugin only needs
    to override ``name`` and ``version`` properties plus ``actions()``.

    Lifecycle::

        loader.load_all()    # call register_plugin(path) for each found dir
        loader.enable_all()  # call plugin.enable() for each loaded plugin
        ...
        loader.disable_all() # call plugin.disable() for each active plugin
        loader.unload_all()  # call plugin.unload() for each loaded plugin

    阶段 1 加固（ADR-026）：``enable()`` 改无参。需上下文的新插件应实现
    ``ContextAwarePlugin``（Registry 启用顺序 ``set_context → enable``）。
    """

    # ── Identity ─────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Return the plugin's display name (stable, unique)."""
        return "unnamed"

    @property
    def version(self) -> str:
        """Return the plugin's version string."""
        return "0.1.0"

    # ── Lifecycle ────────────────────────────────────────────────────────

    def enable(self) -> None:
        """Activate the plugin.

        Implementations should perform any resource allocation here. 阶段 1
        加固（ADR-026）：``enable`` 不再接收 ``context`` 参——上下文注入
        改走 ``ContextAwarePlugin.set_context(context)``（Registry 启用顺序
        ``set_context → enable``）。旧 ``enable(context)`` 签名作兼容路径
        Deprecated 保留一个版本，Registry 用 ``inspect.signature`` 识别。

        The default is a no-op.
        """

    def disable(self) -> None:
        """Deactivate the plugin (called on user disable or app shutdown).

        Implementations should release any resources acquired in ``enable()``.
        The default is a no-op.
        """

    # ── UI contributions ─────────────────────────────────────────────────

    def actions(self) -> list[PluginAction]:
        """Return the list of menu/toolbar actions this plugin contributes.

        Called by the host application after the plugin is loaded and enabled.
        Each ``PluginAction`` describes one clickable command; the host is
        responsible for creating the actual ``QAction`` and connecting its
        triggered signal to ``execute_action()``.

        Returns:
            An empty list by default (passive plugins that only process data
            return an empty list).
        """
        return []

    def execute_action(self, action_id: str) -> "ActionResult":
        """Execute the command identified by ``action_id`` and return a result.

        ``action_id`` matches one of the IDs returned by ``actions()``.
        The host calls this when the user clicks the corresponding menu item,
        then renders the returned ``ActionResult`` to the user (拍板 v2 收敛：
        宿主渲染动作结果——插件不直触 UI/文件系统).

        Args:
            action_id: The stable ``PluginAction.id`` of the action to execute.

        Returns:
            ActionResult with status "success" / "failure" / "noop". When
            ``action_id`` is not owned by this plugin, return ``noop()`` so
            the host continues searching other plugins.
        """
        from photo_archiver.application.dtos.plugin_action_result import noop

        return noop()


class ContextAwarePlugin(Protocol):
    """Context-aware plugin interface — new standard (ADR-026).

    继承 ``Plugin`` 协议形态（``enable + disable + actions + execute_action``）
    并扩一个 ``set_context(context)`` 方法。Registry 启用顺序：
    ``set_context(context) → enable()``。新插件应实现本协议而非旧
    ``enable(context)`` 签名——mypy 静态守护完整，误漏任一方法即编译报错。

    旧 ``enable(context)`` 兼容路径 Deprecated 保留一个版本，移除轮次
    留 v2.0.0 单独裁决。
    """

    @property
    def name(self) -> str:
        """Return the plugin's display name (stable, unique)."""
        return "unnamed"

    @property
    def version(self) -> str:
        """Return the plugin's version string."""
        return "0.1.0"

    def set_context(self, context: "PluginContext") -> None:
        """Inject the host-provided read-only PluginContext.

        Called by the Registry before ``enable()``. Implementations should
        store ``context`` for later use in ``execute_action()``.

        Args:
            context: PluginContext read-only facade — plugins access a limited
                Application Service subset through it. 暴露 search_photos
                + detect_duplicates 读方法，不持 Repository / UnitOfWork /
                ApplicationContext 引用。
        """

    def enable(self) -> None:
        """Activate the plugin (called after ``set_context``)."""

    def disable(self) -> None:
        """Deactivate the plugin."""

    def actions(self) -> list[PluginAction]:
        """Return the list of menu/toolbar actions this plugin contributes."""
        return []

    def execute_action(self, action_id: str) -> "ActionResult":
        """Execute the command identified by ``action_id``."""
        from photo_archiver.application.dtos.plugin_action_result import noop

        return noop()
