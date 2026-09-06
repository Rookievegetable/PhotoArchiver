"""Qt 标准控件文案中文化（ui-rules §24 Internationalization）.

加载 PySide6 自带的 ``qtbase_zh_CN`` 基础翻译，覆盖 Qt 运行时渲染的
标准文字——QDialogButtonBox 标准按钮（保存 / 取消 / 确定 / 关闭）与
QFileDialog、QMessageBox 等系统对话框的按钮。视图内静态文案不经过
此机制（集中在 ``presentation/ui_text.py``）。

翻译目录定位：以 Qt 自报的 ``QLibraryInfo`` 翻译路径为主，轮子相对布局
（Windows 平铺 ``PySide6/translations``、Linux/macOS ``PySide6/Qt/translations``）
为兜底——PySide6 各平台轮子的 Qt 目录布局不同，硬编码单一相对路径会在
非 Windows 平台 miss（2026-09-06 CI run #32–#35 实证）。

带存在性守卫：全部候选目录均未命中时仅告警不阻断启动——标准按钮退回
英文，功能不受影响（发布资产与精简 venv 均默认随 PySide6 携带该文件）。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import PySide6
from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication

from loguru import logger

_TRANSLATIONS_DIRECTORY_NAME = "translations"
_TRANSLATION_CATALOG = "qtbase_zh_CN"


def translation_directory_candidates() -> Sequence[Path]:
    """Return translation directory candidates in priority order."""
    candidates: list[Path] = []
    qt_known = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_known:
        candidates.append(Path(qt_known))
    wheel_dir = Path(PySide6.__file__).resolve().parent
    candidates.append(wheel_dir / _TRANSLATIONS_DIRECTORY_NAME)
    candidates.append(wheel_dir / "Qt" / _TRANSLATIONS_DIRECTORY_NAME)
    return candidates


def install_chinese_ui_translations(app: QApplication) -> bool:
    """Install the bundled Simplified-Chinese Qt base translation.

    Args:
        app: The running ``QApplication``; the translator is parented to it
            so it lives as long as the application.

    Returns:
        ``True`` when the translation was loaded and installed, ``False``
        when no candidate directory contained the catalog (a warning is
        logged; startup continues with English standard texts).
    """
    translator = QTranslator(app)
    candidates = translation_directory_candidates()
    for directory in candidates:
        if translator.load(_TRANSLATION_CATALOG, str(directory)):
            app.installTranslator(translator)
            return True
    logger.warning(
        "Qt 简体中文翻译未找到：已尝试 {}（标准按钮将保持英文）",
        [str(directory) for directory in candidates],
    )
    return False
