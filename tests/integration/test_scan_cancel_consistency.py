"""N3 扫描取消边界一致性 + 重扫幂等（B19 自动化等价物）.

实现期实证（2026-09-06，诊断运行）：扫描的协作取消只在 WorkerTask.run()
**边界**生效（KNOWN_ISSUES LIMIT-002 同型设计）——旗标在起点之后置位不会
中断在途扫描，任务会注册完全部照片后以 completed 终态收尾（实测 2000 张
全部完成、cancel_requested=True）。因此本文件用两个确定性用例覆盖 B19 的
真实不变量：

1. 边界前取消（提交后立即置旗）→ cancelled 终态；库为空或干净子集
   （每行 id/路径/元数据完整，无重复），重扫补齐全量且无重复；
2. 无取消的重扫幂等：扫描部分文件 → 追加文件 → 重扫 → 增量补齐、
   原有照片原样保留、无重复注册。

取代桌面清单 B19 的手工环节；取消终态 UI 复位与单飞守卫释放已由
``test_scan_cancellation.py`` / ``test_scan_single_flight.py`` 覆盖。
不依赖 InsightFace 模型（LIMIT-001 / CI Principle 3）。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from pathlib import Path

from PIL import Image

from photo_archiver.app import bootstrap_application
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views.main_window import MainWindow

HALF_COUNT = 500


def _make_photos(folder: Path, count: int, start: int = 0) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(start, start + count):
        Image.new("RGB", (16, 16), (i % 255, 40, 90)).save(folder / f"p{i:04d}.png")


def _make_window(qtbot, tmp_path: Path) -> MainWindow:
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'consistency.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    window = MainWindow(context)
    qtbot.addWidget(window)
    window.show()
    return window


def _registered_paths(window: MainWindow) -> set[str]:
    return {
        photo.path.raw_path
        for photo in window._context.repositories.photos.list_all()
    }


def _scan_to_completion(window: MainWindow, photo_dir: Path, qtbot) -> None:
    runnable = window._scan_controller.scan_folder(photo_dir)
    assert runnable is not None
    window._connect_scan_signals(runnable)
    qtbot.waitUntil(
        lambda: window._scan_action.isEnabled()
        and not window._scan_controller.is_running,
        timeout=120000,
    )


def test_cancel_at_boundary_leaves_clean_store_and_rescan_completes(
    qtbot, tmp_path: Path
) -> None:
    """边界前取消 → cancelled 终态；库为空或干净子集；重扫补齐全量。"""
    window = _make_window(qtbot, tmp_path)
    photo_dir = tmp_path / "photos"
    _make_photos(photo_dir, 2000)
    repository = window._context.repositories.photos

    runnable1 = window._scan_controller.scan_folder(photo_dir)
    assert runnable1 is not None
    window._connect_scan_signals(runnable1)
    # 提交后立即置旗——抢在 WorkerTask.run() 起点边界之前（确定性取消）。
    runnable1.cancel("User requested cancel")
    assert runnable1.task.is_cancel_requested

    qtbot.waitUntil(
        lambda: "已取消" in window._status_label.text().lower(), timeout=60000
    )
    assert window._scan_action.isEnabled()

    # 干净库断言：取消可能落在起点前（0 行）或边界竞争下少量注册——
    # 两种形态都必须一致（无重复、元数据完整、路径真实存在）。
    subset = repository.list_all()
    subset_paths = _registered_paths(window)
    assert len(subset_paths) == len(subset)
    for photo in subset:
        assert photo.id is not None
        assert Path(photo.path.raw_path).is_file()
        assert photo.captured_at is not None  # 无 EXIF → mtime 兜底

    # 重扫同一目录：补齐全量、无重复、子集原样保留。
    _scan_to_completion(window, photo_dir, qtbot)
    final = repository.list_all()
    assert len(final) == 2000
    assert len(_registered_paths(window)) == 2000
    assert subset_paths <= _registered_paths(window)


def test_rescan_grows_superset_idempotently(qtbot, tmp_path: Path) -> None:
    """部分文件扫描 → 追加文件 → 重扫：增量补齐、原有照片原样保留、无重复。"""
    window = _make_window(qtbot, tmp_path)
    photo_dir = tmp_path / "photos"
    _make_photos(photo_dir, HALF_COUNT)
    repository = window._context.repositories.photos

    _scan_to_completion(window, photo_dir, qtbot)
    first_paths = _registered_paths(window)
    assert len(first_paths) == HALF_COUNT

    _make_photos(photo_dir, HALF_COUNT, start=HALF_COUNT)  # 追加 500 张新文件
    _scan_to_completion(window, photo_dir, qtbot)

    final = repository.list_all()
    assert len(final) == 2 * HALF_COUNT  # 增量补齐
    assert len(_registered_paths(window)) == 2 * HALF_COUNT  # 无重复注册
    assert first_paths <= _registered_paths(window)  # 原有照片原样保留
