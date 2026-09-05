"""P0-1 plugin UI loading chain tests.

Proves the full runtime chain — discovery → load → enable → QAction
registration into the real MainWindow toolbar → user-visible → action
dispatch reaching the report/message rendering — against the real example
plugins and a real bootstrapped context.

Regression guard for the P0-1 defect: the plugin directory anchor resolved
to ``<repo>/src/examples/plugins`` (nonexistent), so the entire chain was
silently skipped at window construction while every backend unit test
stayed green. These tests assert the user-visible outcome, not merely that
the loader object exists.

2026-09-05 UI 整备：示例插件不再随主窗口自动加载（生产工具栏不展示
Say Hello / Import People (Demo) / Stats Report 演示动作）。加载链保持
不变——本测试改为显式驱动同一公开链路（``load_from_path`` →
``enable_all`` → ``_add_plugin_actions``），即外部插件宿主接入真实插件
目录时走过的路径；MainWindow 构造后持空注册表作为扩展点。

Modal boundary doubles (established project policy): PluginReportDialog.exec
and QMessageBox.information are recorded, never executed — everything else in
the chain (loader, plugin exec, execute_action, SQLite reads, signal wiring)
is real.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtWidgets import QToolBar

# Import the app package first so its __init__ finishes initializing before
# MainWindow pulls app.context.ApplicationContext during its own import
# (same ordering note as test_main_window_smoke.py).
from photo_archiver.app import bootstrap_application
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views import main_window as main_window_module
from photo_archiver.presentation.views.main_window import MainWindow

EXPECTED_PLUGIN_NAMES = {"hello", "stats_report", "import_people_demo"}
EXPECTED_PLUGIN_LABELS = {"Say Hello", "Stats Report", "Import People (Demo)"}

# tests/unit/presentation/ → repo root; the source/clone layout is the only
# supported runtime form (ADR-031).
EXAMPLES_PLUGINS_DIR = Path(__file__).resolve().parents[3] / "examples" / "plugins"


def _build_window(qtbot, tmp_path: Path) -> MainWindow:
    """Bootstrap a real context on a throwaway DB and construct MainWindow."""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'plugin_ui.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    return window


def _load_example_plugins(window: MainWindow) -> None:
    """Drive the public plugin UI chain against the real example plugins.

    Mirrors what an external plugin host does with its own plugin directory:
    discover → load → enable → register toolbar QActions.
    """
    window._plugin_registry.load_from_path(EXAMPLES_PLUGINS_DIR)
    window._plugin_registry.enable_all()
    window._add_plugin_actions()


def _toolbar_action_map(window: MainWindow) -> dict:
    """Map toolbar action text → QAction for the real 'Main' toolbar."""
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    return {action.text(): action for action in toolbar.actions()}


def test_main_window_starts_with_empty_plugin_registry(qtbot, tmp_path: Path) -> None:
    """生产工具栏不自动加载示例插件——构造后注册表为空、无插件动作。"""
    window = _build_window(qtbot, tmp_path)

    assert window._plugin_registry.enabled_plugins == {}
    assert not window._plugin_registry.has_errors()
    assert window._plugin_actions == []
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar is not None
    assert not (EXPECTED_PLUGIN_LABELS & set(_toolbar_action_map(window)))


def test_plugin_actions_registered_enabled_and_visible(qtbot, tmp_path: Path) -> None:
    """Explicitly loaded example plugins surface as enabled, visible QActions."""
    window = _build_window(qtbot, tmp_path)
    _load_example_plugins(window)

    enabled = set(window._plugin_registry.enabled_plugins)
    assert EXPECTED_PLUGIN_NAMES <= enabled
    assert not window._plugin_registry.has_errors()

    # UI registration: one real QAction per plugin action, on the real toolbar.
    actions = _toolbar_action_map(window)
    assert EXPECTED_PLUGIN_LABELS <= set(actions)
    for label in EXPECTED_PLUGIN_LABELS:
        assert actions[label].isEnabled()
        assert actions[label].toolTip() != ""

    # User-visible: with the window shown, plugin actions are on screen.
    window.show()
    toolbar = window.findChild(QToolBar, "Main")
    assert toolbar.isVisible()
    for qaction in window._plugin_actions:
        assert qaction.isVisible()


def test_plugin_action_dispatch_reaches_report_dialog(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """Triggering the real Stats Report QAction must render a real report.

    StatsReportPlugin.execute_action runs for real (PluginContext reads the
    real SQLite library); only the modal exec is doubled.
    """
    window = _build_window(qtbot, tmp_path)
    _load_example_plugins(window)
    actions = _toolbar_action_map(window)

    constructed: list[str] = []
    executed: list[int] = []

    class RecordingDialog:
        def __init__(self, report, parent=None) -> None:
            constructed.append(report.title)

        def exec(self) -> int:
            executed.append(1)
            return 0

    monkeypatch.setattr(
        main_window_module, "PluginReportDialog", RecordingDialog
    )

    actions["Stats Report"].trigger()

    assert constructed == ["Photo Library Stats"]
    assert executed == [1]


def test_plugin_action_without_report_shows_message(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """A success result without a report renders an information message."""
    window = _build_window(qtbot, tmp_path)
    _load_example_plugins(window)
    actions = _toolbar_action_map(window)

    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda parent, title, text: messages.append((title, text)),
    )

    actions["Say Hello"].trigger()

    assert len(messages) == 1
    title, text = messages[0]
    assert title == "插件：hello.greet"
    assert "Hello" in text
