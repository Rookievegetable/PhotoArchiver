"""Application lifecycle coordination."""

from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from photo_archiver.app.context import ApplicationContext
from photo_archiver.app.repositories import ApplicationRepositories
from photo_archiver.app.services import ApplicationServices
from photo_archiver.presentation.translations import install_chinese_ui_translations
from photo_archiver.presentation.views.main_window import MainWindow


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
