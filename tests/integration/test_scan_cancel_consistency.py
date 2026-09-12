"""N3 扫描取消一致性 + 重扫幂等（B19 自动化等价物）.

实现期实证（2026-09-06，Windows/ubuntu 双向）：扫描的协作取消只在
WorkerTask.run() **边界**生效（KNOWN_ISSUES LIMIT-002/006）——"提交后立即
置旗"与 worker 线程启动存在竞速，两种终态都合法：抢到边界 → cancelled +
空/小子集；没抢到 → 在途扫描自然扫完 → completed + 全量。因此取消用例
对**两种结局**断言同一组不变量（终态必达、库一致、重扫归一全量），不以
竞速归属为前提。

第二个用例覆盖无取消的增量重扫幂等：部分扫描 → 追加文件 → 重扫 →
增量补齐、原有照片原样保留、无重复注册。

取代桌面清单 B19 的手工环节；取消终态 UI 复位与单飞守卫释放已由
``test_scan_cancellation.py``（win/linux）/ ``test_scan_single_flight.py``
覆盖。不依赖 InsightFace 模型（LIMIT-001 / CI Principle 3）。
"""

import pytest
import os
import sys

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


@pytest.mark.skipif(
    sys.platform == "darwin" and os.environ.get("PA_ALLOW_LIMIT_006") != "1",
    reason="LIMIT-006: macOS runner native segfault (signal 11) in the scan worker "
    "(pathlib.is_file/stat) during real-executor stress scans with qtbot.waitUntil; "
    "win/linux unaffected — see KNOWN_ISSUES",
)
def test_cancel_request_leaves_consistent_store_and_rescan_completes(
    qtbot, tmp_path: Path
) -> None:
    """取消请求后库必一致；重扫归一为全量、无重复。

    取消旗标只在 WorkerTask.run() 边界生效（LIMIT-002/006）："提交后立即
    置旗"与 worker 线程启动存在竞速，两种终态都合法且已双向实证
    （Windows 抢到 → cancelled + 空库；ubuntu 未抢到 → 扫完 2000 +
    completed）。用例对两种结局做同一组不变量断言：终态必达（cancelled
    或 completed 二者其一）、库无重复且每行完整、重扫后恰为全量、取消前
    已注册照片原样保留。
    """
    window = _make_window(qtbot, tmp_path)
    photo_dir = tmp_path / "photos"
    _make_photos(photo_dir, 2000)
    repository = window._context.repositories.photos

    runnable1 = window._scan_controller.scan_folder(photo_dir)
    assert runnable1 is not None
    window._connect_scan_signals(runnable1)
    runnable1.cancel("User requested cancel")
    assert runnable1.task.is_cancel_requested

    # 终态必达（cancelled 或 completed 二者其一；竞速归属不作前提）。
    qtbot.waitUntil(
        lambda: "已取消" in window._status_label.text().lower()
        or "完成" in window._status_label.text().lower(),
        timeout=120000,
    )
    assert window._scan_action.isEnabled()

    # 两种终态下的库都必须一致：无重复、元数据完整、路径真实存在。
    subset = repository.list_all()
    subset_paths = _registered_paths(window)
    assert len(subset_paths) == len(subset)
    assert len(subset) <= 2000
    for photo in subset:
        assert photo.id is not None
        assert Path(photo.path.raw_path).is_file()
        assert photo.captured_at is not None  # 无 EXIF → mtime 兜底

    # 重扫同一目录：两种终态都归一为全量、无重复、子集原样保留。
    _scan_to_completion(window, photo_dir, qtbot)
    final = repository.list_all()
    assert len(final) == 2000
    assert len(_registered_paths(window)) == 2000
    assert subset_paths <= _registered_paths(window)


@pytest.mark.skipif(
    sys.platform == "darwin" and os.environ.get("PA_ALLOW_LIMIT_006") != "1",
    reason="LIMIT-006: macOS runner native segfault (signal 11) in the scan worker "
    "(pathlib.is_file/stat) during real-executor stress scans with qtbot.waitUntil; "
    "win/linux unaffected — see KNOWN_ISSUES",
)
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
