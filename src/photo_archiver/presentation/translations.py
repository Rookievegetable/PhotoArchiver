"""Qt 标准控件文案中文化（ui-rules §24 Internationalization）.

加载 PySide6 自带的 ``qtbase_zh_CN`` 基础翻译，覆盖 Qt 运行时渲染的
标准文字——QDialogButtonBox 标准按钮（保存 / 取消 / 确定 / 关闭）与
QFileDialog、QMessageBox 等系统对话框的按钮。视图内静态文案不经过
此机制（集中在 ``presentation/ui_text.py``）。

带存在性守卫：翻译目录/文件缺失仅告警不阻断启动——标准按钮退回
英文，功能不受影响（发布资产与精简 venv 均默认随 PySide6 携带该文件）。
"""

from __future__ import annotations

from pathlib import Path

import PySide6
from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import QApplication

from loguru import logger

_TRANSLATIONS_DIRECTORY_NAME = "translations"
_TRANSLATION_CATALOG = "qtbase_zh_CN"


def install_chinese_ui_translations(app: QApplication) -> bool:
    """Install the bundled Simplified-Chinese Qt base translation.

    Args:
        app: The running ``QApplication``; the translator is parented to it
            so it lives as long as the application.

    Returns:
        ``True`` when the translation was loaded and installed, ``False``
        when the catalog was not found (a warning is logged; startup
        continues with English standard texts).
    """
    translations_dir = (
        Path(PySide6.__file__).resolve().parent / _TRANSLATIONS_DIRECTORY_NAME
    )
    translator = QTranslator(app)
    if not translator.load(_TRANSLATION_CATALOG, str(translations_dir)):
        logger.warning(
            "Qt 简体中文翻译未找到：{}（标准按钮将保持英文）", translations_dir
        )
        return False
    app.installTranslator(translator)
    return True
