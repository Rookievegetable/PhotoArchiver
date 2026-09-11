"""Configurable plugin directory loading — ADR-038 (ISSUE-020 resolution ①).

体检 N-1：``_add_plugin_actions()`` 此前生产零调用，插件动作对真实用户不可
见。裁决①恢复对外承诺：设置 ``PLUGINS_DIRECTORY`` 后，启动即从该目录
``load_from_path → enable_all → _add_plugin_actions``，动作挂载到主工具栏。

真实 MainWindow + 真实 PluginRegistry + 真实文件系统驱动；插件文件在
tmp_path 内即席生成（覆盖标准加载 / 目录缺失 / 坏插件隔离三种形态）。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from textwrap import dedent

from photo_archiver.presentation.views.main_window import MainWindow

_GOOD_PLUGIN = dedent(
    """
    from photo_archiver.application.dtos.plugin_action_result import ActionResult
    from photo_archiver.application.ports.plugin import PluginAction


    class _DirectoryLoadedPlugin:
        @property
        def name(self) -> str:
            return "directory-loaded"

        @property
        def version(self) -> str:
            return "1.0.0"

        def set_context(self, context) -> None:
            self._context = context

        def enable(self) -> None:
            pass

        def disable(self) -> None:
            pass

        def actions(self):
            return [PluginAction(id="directory-loaded.ping", label="目录插件示例动作", tooltip="ADR-038")]

        def execute_action(self, action_id):
            return success("pong")

    plugin = _DirectoryLoadedPlugin()
    """
)

_PLUGIN_SOURCE_FILE = "good_plugin.py"


def _write_plugin(directory, source: str, filename: str = _PLUGIN_SOURCE_FILE) -> None:
    (directory / filename).write_text(dedent(source), encoding="utf-8")


def test_window_loads_plugins_from_configured_directory_and_mounts_actions(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    """ADR-038 主链路：配置目录 → 加载 → 启用 → 工具栏动作挂载。"""
    plugins_dir = tmp_path / "my-plugins"
    plugins_dir.mkdir()
    _write_plugin(plugins_dir, _GOOD_PLUGIN)

    context = make_sqlite_context("plugins_loaded.db", plugins_directory=plugins_dir)
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert window._plugin_registry.enabled_plugins.keys() == {"directory-loaded"}
    assert len(window._plugin_actions) == 1
    action = window._plugin_actions[0]
    assert action.text() == "目录插件示例动作"
    assert action.toolTip() == "ADR-038"
    # 动作真实挂在主工具栏上（对外承诺：用户可见）。
    from PySide6.QtWidgets import QToolBar

    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    assert action in toolbar.actions()


def test_window_without_plugins_directory_loads_nothing(
    qtbot, make_sqlite_context
) -> None:
    """默认（未配置 PLUGINS_DIRECTORY）零加载——与既有决策零破坏。"""
    context = make_sqlite_context("plugins_none.db")
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert window._plugin_registry.plugins == {}
    assert window._plugin_actions == []


def test_window_with_missing_plugin_directory_starts_cleanly(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    """配置了不存在的目录：注册表警告并跳过，宿主正常启动、无动作挂载。"""
    context = make_sqlite_context(
        "plugins_missing.db", plugins_directory=tmp_path / "nowhere"
    )
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert window._plugin_actions == []
    assert window._plugin_registry.plugins == {}


def test_window_isolates_broken_plugin_and_loads_the_rest(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    """坏插件（语法错误）被错误隔离跳过，同目录好插件照常加载（ADR-026）。"""
    plugins_dir = tmp_path / "mixed-plugins"
    plugins_dir.mkdir()
    _write_plugin(plugins_dir, _GOOD_PLUGIN)
    (plugins_dir / "broken_plugin.py").write_text(
        "this is not valid python (((\n", encoding="utf-8"
    )

    context = make_sqlite_context("plugins_mixed.db", plugins_directory=plugins_dir)
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert window._plugin_registry.enabled_plugins.keys() == {"directory-loaded"}
    assert window._plugin_registry.has_errors()  # 坏插件隔离留痕
    assert len(window._plugin_actions) == 1
