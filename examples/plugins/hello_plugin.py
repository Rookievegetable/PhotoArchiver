"""Hello Plugin — minimal Plugin System example（阶段 1 ContextAwarePlugin 标准）.

演示 ADR-026 拍板的新标准插件协议——``ContextAwarePlugin``：
``set_context(context) → enable() → actions() / execute_action()``。
HelloPlugin 是纯声明式插件（不消费 Context），但演示完整新标准签名。

旧 ``enable(context)`` 兼容路径已于 v2.0.0 移除（ADR-030）——外部插件须迁移
至本文件的 ``set_context + enable`` 标准形态，详见 ``docs/development/plugin-guide.md``。
"""

from __future__ import annotations

from loguru import logger

from photo_archiver.application.dtos.plugin_action_result import ActionResult, noop, success
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext


class HelloPlugin:
    """A minimal plugin demonstrating the ContextAwarePlugin standard (ADR-026)."""

    @property
    def name(self) -> str:
        """Return the stable display name."""
        return "hello"

    @property
    def version(self) -> str:
        """Return the plugin version."""
        return "1.1.0"

    def set_context(self, context: PluginContext) -> None:
        """Store the host-provided read-only PluginContext.

        HelloPlugin is declarative-only — context is accepted to demonstrate
        the ContextAwarePlugin standard but unused in execute_action().
        """
        self._context: PluginContext = context
        logger.debug("HelloPlugin received context (unused — declarative plugin)")

    def enable(self) -> None:
        """Log activation. Context (if any) was injected via set_context before this."""
        logger.info("HelloPlugin enabled")

    def disable(self) -> None:
        """Log deactivation."""
        logger.info("HelloPlugin disabled")

    def actions(self) -> list[PluginAction]:
        """Register one 'Hello World' menu action."""
        return [
            PluginAction(
                id="hello.greet",
                label="Say Hello",
                tooltip="Display a friendly greeting from the Hello plugin",
            ),
        ]

    def execute_action(self, action_id: str) -> ActionResult:
        """Execute the requested action by its ID, returning a structured result."""
        if action_id == "hello.greet":
            logger.info("Hello from the HelloPlugin!")
            return success(message="Hello from the HelloPlugin!")
        return noop()


# Module-level export the loader discovers.
plugin = HelloPlugin()
