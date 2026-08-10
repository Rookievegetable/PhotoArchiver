"""Plugin discovery and loading for Step 15 Plugin System.

Loads plugins from the ``examples/plugins/`` directory or from external paths
provided at runtime. Each plugin is a Python module that exports a ``plugin``
attribute conforming to the ``Plugin`` protocol.

Error handling: malformed/error plugins are logged and skipped; a single bad
plugin never crashes the host application (acceptance criterion 3).
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
        """Call ``enable()`` on every loaded plugin, injecting the context."""
        for name, plugin in self._plugins.items():
            try:
                plugin.enable(self._context)
                self._enabled.add(name)
                logger.info("Plugin enabled: {}", name)
            except Exception:
                logger.exception("Failed to enable plugin: {}", name)
                self._errors.append((name, "enable() raised an exception"))

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
        for attr in ("name", "version", "enable", "disable"):
            if not callable(getattr(raw, attr, None)) and attr not in ("name", "version"):
                pass  # properties are okay even if not callable
            if attr in ("name", "version") and not isinstance(getattr(raw, attr, None), str):
                msg = f"{module_name}.plugin.{attr} is not a string property"
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
