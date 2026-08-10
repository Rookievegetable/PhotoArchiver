"""Unit tests for the Step 15 Plugin System loader.

Verifies:
- Loading a valid plugin from a directory
- Plugin entries in the registry are accessible
- Error handling for missing directories, missing plugin attributes
- Lifecycle enable/disable
- Loading duplicate names is rejected
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from photo_archiver.plugins import PluginRegistry


class TestPluginRegistry:
    """Plugin registry unit tests."""

    def test_load_valid_plugin(self) -> None:
        """Load a valid plugin and verify it appears in the registry."""
        with TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            plugin_file = plugin_dir / "hello.py"
            plugin_file.write_text("""
from photo_archiver.application.ports.plugin import Plugin

class _HelloPlugin:
    name = "hello"
    version = "1.0.0"
    def enable(self): pass
    def disable(self): pass
    def actions(self): return []
    def execute_action(self, action_id): pass

plugin = _HelloPlugin()
""")
            registry = PluginRegistry()
            registry.load_from_path(plugin_dir)

            assert "hello" in registry.plugins
            assert registry.plugins["hello"].version == "1.0.0"
            assert not registry.has_errors()

    def test_load_from_missing_directory_logs_warning(self) -> None:
        """Loading from a non-existent directory produces no plugins."""
        registry = PluginRegistry()
        registry.load_from_path(Path("/nonexistent/plugins"))
        assert len(registry.plugins) == 0

    def test_skip_module_without_plugin_attr(self) -> None:
        """A Python file without a 'plugin' attribute is skipped."""
        with TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / "bad.py").write_text("x = 1\\n")
            registry = PluginRegistry()
            registry.load_from_path(plugin_dir)

            assert len(registry.plugins) == 0
            assert registry.has_errors()

    def test_enable_disable_lifecycle(self) -> None:
        """enable_all / disable_all should call the lifecycle methods."""
        with TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / "lifecycle.py").write_text("""
class _LifecyclePlugin:
    name = "lifecycle"
    version = "0.1.0"
    enabled_flag = False
    disabled_flag = False
    def enable(self, context=None):
        self.enabled_flag = True
    def disable(self):
        self.disabled_flag = True
    def actions(self): return []
    def execute_action(self, action_id): pass

plugin = _LifecyclePlugin()
""")
            registry = PluginRegistry()
            registry.load_from_path(plugin_dir)

            # Initially not enabled
            assert "lifecycle" not in registry.enabled_plugins

            registry.enable_all()
            assert "lifecycle" in registry.enabled_plugins
            assert getattr(registry.plugins["lifecycle"], "enabled_flag", False)

            registry.disable_all()
            assert "lifecycle" not in registry.enabled_plugins
            assert getattr(registry.plugins["lifecycle"], "disabled_flag", False)

    def test_duplicate_name_skipped(self) -> None:
        """A second plugin with the same name is skipped."""
        with TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / "dup_a.py").write_text("""
class _DupPlugin:
    name = "duplicate"
    version = "1"
    def enable(self): pass
    def disable(self): pass
    def actions(self): return []
    def execute_action(self, action_id): pass
plugin = _DupPlugin()
""")
            (plugin_dir / "dup_b.py").write_text("""
class _DupPlugin:
    name = "duplicate"
    version = "2"
    def enable(self): pass
    def disable(self): pass
    def actions(self): return []
    def execute_action(self, action_id): pass
plugin = _DupPlugin()
""")
            registry = PluginRegistry()
            registry.load_from_path(plugin_dir)

            # Only one "duplicate" plugin; version will be the first loaded
            assert len(registry.plugins) == 1
            assert registry.has_errors()

    def test_load_all_multiple_paths(self) -> None:
        """load_all with multiple directories loads plugins from each."""
        with TemporaryDirectory() as tmp_a, TemporaryDirectory() as tmp_b:
            dir_a = Path(tmp_a)
            dir_b = Path(tmp_b)

            (dir_a / "alpha.py").write_text("""
class _Alpha:
    name = "alpha"; version = "1.0.0"
    def enable(self): pass
    def disable(self): pass
    def actions(self): return []
    def execute_action(self, action_id): pass
plugin = _Alpha()
""")
            (dir_b / "beta.py").write_text("""
class _Beta:
    name = "beta"; version = "2.0.0"
    def enable(self): pass
    def disable(self): pass
    def actions(self): return []
    def execute_action(self, action_id): pass
plugin = _Beta()
""")

            registry = PluginRegistry()
            registry.load_all(dir_a, dir_b)

            assert "alpha" in registry.plugins
            assert "beta" in registry.plugins
            assert len(registry.plugins) == 2
