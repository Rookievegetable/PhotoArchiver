"""Hello Plugin — minimal Step 15 Plugin System example.

This plugin exercises the full Plugin protocol: identity, lifecycle, and a
single menu action. It serves as both a smoke test for the loader and a
template for third-party plugin authors.
"""

from loguru import logger

from photo_archiver.application.ports.plugin import PluginAction


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

    def enable(self) -> None:
        """Log activation."""
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

    def execute_action(self, action_id: str) -> None:
        """Execute the requested action by its ID."""
        if action_id == "hello.greet":
            logger.info("Hello from the HelloPlugin!")


# Module-level export the loader discovers.
plugin = HelloPlugin()
