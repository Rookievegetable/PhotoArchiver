"""Plugin port protocol for Step 15 Plugin System.

Defines the ``Plugin`` interface that all plugins must implement. The interface
lives in the Application layer port boundary so that plugins (which may reside
in external packages) depend only on Application public API, never on
Infrastructure internals (DEP-060/061/062).

The Application and Presentation layers consume plugins through this protocol
without importing concrete plugin classes — core code never depends on any
specific plugin (acceptance criterion 1).
"""

from __future__ import annotations

from typing import Protocol


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
        """Activate the plugin (called after loading or on user enable).

        Implementations should perform any resource allocation here.
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

    def execute_action(self, action_id: str) -> None:
        """Execute the command identified by ``action_id``.

        ``action_id`` matches one of the IDs returned by ``actions()``.
        The host calls this when the user clicks the corresponding menu item.

        Args:
            action_id: The stable ``PluginAction.id`` of the action to execute.
        """
