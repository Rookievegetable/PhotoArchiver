"""Archive-root preference resolution — G-2 (FEAT-14 closure).

UserPreferences.archive_root（设置 UI）优先于 AppSettings.ARCHIVE_ROOT（.env）；
两者皆未配置时归档入口保持既有的"未配置"警示流。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")


from photo_archiver.application.dtos.settings import UserPreferences
from photo_archiver.app import ui_assembly as ui_assembly_module
from photo_archiver.presentation.views.main_window import MainWindow


@pytest.fixture(autouse=True)
def _isolated_qsettings(monkeypatch, tmp_path):
    """Point the rebind QSettings at a throwaway INI file.

    ``_rebind_settings_service_to_qsettings`` targets the real machine-wide
    QSettings (registry / plists); without isolation one test's saved
    preference leaks into every later test and process.
    """
    from PySide6.QtCore import QSettings

    ini = tmp_path / "prefs.ini"
    monkeypatch.setattr(
        ui_assembly_module,
        "QSettings",
        lambda *args, **kwargs: QSettings(str(ini), QSettings.Format.IniFormat),
    )


def test_effective_archive_root_falls_back_to_settings_when_preference_unset(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    context = make_sqlite_context(
        "archive_root_env.db", archive_root=tmp_path / "env-root"
    )
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert window._effective_archive_root() == tmp_path / "env-root"


def test_effective_archive_root_preference_wins_over_settings(
    qtbot, make_sqlite_context, tmp_path
) -> None:
    context = make_sqlite_context(
        "archive_root_pref.db", archive_root=tmp_path / "env-root"
    )
    window = MainWindow(context)
    qtbot.addWidget(window)
    # ui_assembly 在窗口构造时把 settings 服务重绑到 QSettings 存储——
    # 因此偏好必须在构造之后写入（与真实使用顺序一致）。
    context.services.settings.save(
        UserPreferences(archive_root=tmp_path / "pref-root")
    )

    assert window._effective_archive_root() == tmp_path / "pref-root"


def test_effective_archive_root_none_when_neither_configured(
    qtbot, make_sqlite_context
) -> None:
    context = make_sqlite_context("archive_root_none.db")
    window = MainWindow(context)
    qtbot.addWidget(window)

    assert window._effective_archive_root() is None
