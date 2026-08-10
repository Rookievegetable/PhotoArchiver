"""Hello Plugin — minimal Step 15 Plugin System example.

This plugin exercises the full Plugin protocol: identity, lifecycle, and a
single menu action. It serves as both a smoke test for the loader and a
template for third-party plugin authors.

B5 v2 收敛：enable 扩可选 context 参（HelloPlugin 纯声明不消费 Context）+
execute_action 改返 ActionResult（宿主渲染动作结果）。
"""

from __future__ import annotations

from loguru import logger

from photo_archiver.application.dtos.plugin_action_result import ActionResult, noop, success
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext


class HelloPlugin:
    """A minimal plugin that registers a single 'Hello' action."""

    @property
    def name(self) -> str:
        """Return the stable display name."""
        return "hello"

    @property
    def version(self) -> str:
        """Return the plugin version."""
        return "1.0.0"

    def enable(self, context: PluginContext | None = None) -> None:
        """Log activation. context unused — HelloPlugin is declarative-only."""
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
