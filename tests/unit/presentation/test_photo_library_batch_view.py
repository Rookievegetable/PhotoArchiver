"""照片库批次轴（追加轮 22）——按识别运行查看照片 + 删除入口启停.

与人员名单的批次筛选同构：下拉选具体运行 → 墙面只显示该运行输入快照内
的照片；「删除该批次…」仅在有选中运行时可用。真实 bootstrap + 真实
SQLite（冒烟同构），不弹模态。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from photo_archiver.app import bootstrap_application
from photo_archiver.domain import (
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views.main_window import MainWindow

_BASE_ISO = "2026-10-28T08:00:00"


def _seed(tmp_path: Path):
    """两张照片：photo_0 挂在 run 快照内，photo_1 不挂（用于验证过滤）。"""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'batch.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    repos = context.repositories
    run = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run)
    photos = []
    for index in range(2):
        photo_file = tmp_path / f"photo_{index}.jpg"
        photo_file.write_bytes(b"x")
        photo = Photo(
            path=PhotoPath(photo_file, PhotoPathBase.ABSOLUTE),
            original_name=photo_file.name,
            captured_at=None,
        )
        repos.photos.add(photo)
        photos.append(photo)
    repos.recognition_runs.add_run_photos(run.id, [RunPhotoSnapshot(
        run_id=run.id, photo_id=photos[0].id,
        raw_path="photo_0.jpg", captured_at=None,
    )])
    return context, run, photos


def test_library_batch_combo_filters_photo_wall(qtbot, tmp_path: Path) -> None:
    """选中运行 → 墙面只剩该运行快照内的照片；全部照片 → 不过滤。"""
    context, run, photos = _seed(tmp_path)
    window = MainWindow(context)
    qtbot.addWidget(window)

    combo = window._library_run_combo
    assert combo.count() == 2  # 全部照片 + 1 个运行
    assert combo.itemData(0) is None
    assert combo.itemData(1) == run.id
    assert window._library_delete_run_button.isEnabled() is False

    window._refresh_photo_list()
    assert window._photo_list_model.rowCount() == 2

    combo.setCurrentIndex(1)  # 选中运行
    assert window._library_run_filter_id == run.id
    assert window._library_delete_run_button.isEnabled() is True
    assert window._photo_list_model.rowCount() == 1  # 只有快照内照片
    # 过滤后的身份映射只含快照内照片（详情/导出口径一致）
    assert set(window._photos_by_id) == {photos[0].id}

    combo.setCurrentIndex(0)  # 回到全部照片
    assert window._library_run_filter_id is None
    assert window._library_delete_run_button.isEnabled() is False
    assert window._photo_list_model.rowCount() == 2


def test_library_batch_combo_survives_refresh(qtbot, tmp_path: Path) -> None:
    """刷新重填下拉时值扫描保持当前选择（新扫描不丢批次轴状态）。"""
    context, run, _photos = _seed(tmp_path)
    window = MainWindow(context)
    qtbot.addWidget(window)
    window._library_run_combo.setCurrentIndex(1)
    window._refresh_photo_list()  # 模拟任务完成后的刷新链
    assert window._library_run_combo.currentIndex() == 1
    assert window._library_run_filter_id == run.id
    assert window._library_run_combo.count() == 2
