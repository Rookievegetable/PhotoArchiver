"""追加轮 25（Owner 实机）：扫描即识别完成后人员页聚类卡必须刷新.

scan_photos 任务会创建识别运行（提取特征 N 张）——但 ``_refresh_task_results``
此前只在 ``face_clustering`` 终态重读聚类卡，导致特征数据下拉停在构建期
空态、「运行人脸聚类」保持灰色（重启才恢复）。真实 bootstrap + 真实
SQLite（冒烟同构）：预置识别运行 → 触发 scan_photos 终态刷新 → 断言下拉
出现该运行且聚类键可用。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from photo_archiver.app import bootstrap_application
from photo_archiver.domain import RecognitionRun
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views.main_window import MainWindow


def test_scan_completion_refreshes_clustering_card(qtbot, tmp_path: Path) -> None:
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'scan.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    run = RecognitionRun(parameters={})
    context.repositories.recognition_runs.add_run(run)

    window = MainWindow(context)
    qtbot.addWidget(window)
    page = window._people_admin_page

    # 构建期即应能看到运行（页面自刷新）；随后模拟扫描终态前的陈旧态：
    page.refresh_clustering()
    assert page._cluster_run_combo.count() == 1
    assert page._cluster_run_button.isEnabled() is True

    # 回归点：scan_photos 终态刷新链必须重读聚类卡（此前缺失——停在空态）。
    page._cluster_run_combo.blockSignals(True)
    page._cluster_run_combo.clear()  # 模拟陈旧空态（构建期无运行的残留显示）
    page._cluster_run_combo.blockSignals(False)
    assert page._cluster_run_combo.count() == 0

    window._refresh_task_results("scan_photos")

    assert page._cluster_run_combo.count() == 1  # 运行重新上拉
    assert page._cluster_run_button.isEnabled() is True  # 聚类键恢复可用


def test_clustering_completion_still_refreshes_clustering_card(
    qtbot, tmp_path: Path,
) -> None:
    """face_clustering 终态的原有刷新行为不回归。"""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'cluster.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    run = RecognitionRun(parameters={})
    context.repositories.recognition_runs.add_run(run)
    window = MainWindow(context)
    qtbot.addWidget(window)
    page = window._people_admin_page
    page._cluster_run_combo.blockSignals(True)
    page._cluster_run_combo.clear()
    page._cluster_run_combo.blockSignals(False)

    window._refresh_task_results("face_clustering")

    assert page._cluster_run_combo.count() == 1
