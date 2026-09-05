"""UI 中文化守护测试：Qt 基础翻译装载 + 设置选项域同步（2026-09-05 UI 轮）。

- ``install_chinese_ui_translations``：qtbase_zh_CN 随 PySide6 分发时应成功
  安装（QDialogButtonBox 标准按钮随之中文化）；翻译目录缺失时诚实返回
  False 并告警，不阻断启动。
- ``SETTINGS_THEME_CHOICES`` / ``SETTINGS_LANGUAGE_CHOICES`` 的值域必须与
  Application 层 ``VALID_THEMES`` / ``VALID_LANGUAGES`` 逐项同步——显示映射
  漂移会让持久化值在下拉中找不到（回填守卫静默回退首项）。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialogButtonBox

from photo_archiver.application.dtos.settings import VALID_LANGUAGES, VALID_THEMES
from photo_archiver.presentation.translations import install_chinese_ui_translations
from photo_archiver.presentation.ui_text import (
    SETTINGS_LANGUAGE_CHOICES,
    SETTINGS_THEME_CHOICES,
)


def test_installs_bundled_chinese_translation(qtbot) -> None:
    """PySide6 自带 qtbase_zh_CN 时安装成功，标准按钮渲染为中文。"""
    app = QApplication.instance()
    assert app is not None

    assert install_chinese_ui_translations(app) is True
    # qtbase_zh_CN 将 Save 标准按钮译为"保存"——translators 生效的直接证据。
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
    assert box.button(QDialogButtonBox.StandardButton.Save).text() == "保存"


def test_returns_false_when_catalog_missing(qtbot, tmp_path, monkeypatch) -> None:
    """翻译目录缺失 → 返回 False（告警不阻断），不安装空翻译器。"""
    app = QApplication.instance()
    assert app is not None

    import photo_archiver.presentation.translations as translations_module

    monkeypatch.setattr(
        translations_module,
        "_TRANSLATIONS_DIRECTORY_NAME",
        str(tmp_path / "no_such_translations"),
    )
    # 目录名被替换为不存在路径后，load 以之为父目录必然失败。
    assert translations_module.install_chinese_ui_translations(app) is False


def test_settings_choice_values_mirror_application_contract() -> None:
    """显示映射的值域与 VALID_THEMES/VALID_LANGUAGES 逐项同步（防漂移）。"""
    assert [value for _, value in SETTINGS_THEME_CHOICES] == list(VALID_THEMES)
    assert [value for _, value in SETTINGS_LANGUAGE_CHOICES] == list(VALID_LANGUAGES)
