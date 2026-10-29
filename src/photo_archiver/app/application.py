"""Application lifecycle coordination."""

from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from photo_archiver.app.context import ApplicationContext
from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.app.services import ApplicationServices
from photo_archiver.application.use_cases import SettingsUseCase
from photo_archiver.presentation.translations import install_chinese_ui_translations
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.presentation.visual_style import (
    apply_visual_system,
    detect_platform_scheme,
    resolve_theme,
)


def apply_startup_theme(qt_application: QApplication, settings_service: SettingsUseCase) -> str:
    """Resolve the persisted theme preference and install the themed visual system.

    P0-2/P0-3 最小接线（v1.3.4 §6.2）：GUI 启动链读取已持久化的主题偏好
    （bootstrap 已在 build_ui_controllers 中把 SettingsService 换绑为
    QSettings-backed store），按 DEC-03 解析（system→按启动时系统亮暗；
    light/dark 直取；缺失/非法→DEFAULT_THEME 回退），应用对应主题的视觉
    系统。**唯一评估时刻＝应用启动**（§6.3 事件定义；DEC-02=A：设置页保存
    仅持久化、重启生效；DEC-03=A：不监听 OS 运行中亮暗变化）——本函数只在
    启动链调用一次，运行期无任何重评估/切换入口。

    Returns:
        The resolved theme ("light" / "dark") actually applied.
    """
    preferences = settings_service.load()
    theme = resolve_theme(preferences.theme, detect_platform_scheme(qt_application))
    apply_visual_system(qt_application, theme=theme)
    return theme


class PhotoArchiverApplication:
    """Coordinate the Qt application lifecycle for PhotoArchiver."""

    def __init__(self, arguments: Sequence[str], context: ApplicationContext) -> None:
        """Initialize the desktop application.

        Args:
            arguments: Command-line arguments passed to Qt.
            context: Runtime dependencies assembled during startup.
        """
        self._context = context
        self._qt_application = QApplication(list(arguments))
        # Batch 7：集中视觉体系（按钮层级/焦点环/空态卡片）在窗口构造前
        # 一次性安装——唯一 setStyleSheet 调用点，Widget 内零散布。
        # 阶段 1（P0-2/P0-3）：主题按启动时读取的持久化偏好解析后安装。
        apply_startup_theme(self._qt_application, self._context.services.settings)
        # Qt 标准按钮/系统对话框（保存/取消/确定/关闭、文件选择框）中文化——
        # 尽早于窗口构造前安装；缺失仅告警（presentation.translations）。
        install_chinese_ui_translations(self._qt_application)
        self._main_window = MainWindow(context)

    @property
    def context(self) -> ApplicationContext:
        """Return the assembled runtime application context."""
        return self._context

    @property
    def settings(self):
        """Return application configuration."""
        return self._context.settings

    @property
    def repositories(self) -> ApplicationRepositories:
        """Return assembled repository dependencies."""
        return self._context.repositories

    @property
    def services(self) -> ApplicationServices:
        """Return assembled use case services."""
        return self._context.services

    def run(self) -> int:
        """Show the main window and run the Qt event loop.

        Returns:
            The Qt application exit code.
        """
        self._main_window.show()
        return self._qt_application.exec()
