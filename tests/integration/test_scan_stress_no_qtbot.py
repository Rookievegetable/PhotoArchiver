"""LIMIT-006 D-3 experiment: scan stress WITHOUT qtbot (Phase G G-3).

2026-09-10 起 macOS CI 的原生段错误（LIMIT-006）只观测于"真实 QThreadPool
扫描 worker + 大目录 + qtbot.waitUntil 主线程等待"的组合。本模块把变量拆开：

    test_scan_stress_direct            纯服务调用，无 Qt 线程
    test_scan_stress_via_qthread_pool  真实 QThreadPool + 真实扫描 worker，
                                       主线程 time.sleep 轮询——不经 qtbot

若专属 CI job 中 B 形态仍段错误 → 嫌疑转向 QThreadPool × 大目录本身；
若稳定通过 → 嫌疑收敛到 qtbot 主线程等待交互。两种结果都缩小 D-3 的
追查面（KNOWN_ISSUES LIMIT-006）。

仅当 ``PA_STRESS=1`` 时运行（专属 CI job / 本地手动），常规套件不含。
"""

import os
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from photo_archiver.application.commands import ScanAndRegisterPhotosCommand

pytestmark = pytest.mark.skipif(
    os.environ.get("PA_STRESS") != "1",
    reason="stress matrix runs only in the dedicated PA_STRESS job (LIMIT-006 D-3)",
)

_FILE_COUNT = 2000
_TIMEOUT_SECONDS = 180


def _make_photo_tree(root: Path, count: int) -> Path:
    """Write ``count`` tiny real JPEGs under ``root/photos``."""
    from PIL import Image

    photos = root / "photos"
    photos.mkdir(parents=True)
    image = Image.new("RGB", (4, 4), color=(120, 160, 90))
    for index in range(count):
        image.save(photos / f"img_{index:05}.jpg", format="JPEG")
    return photos


def _make_context(tmp_path: Path):
    from photo_archiver.app import bootstrap_application
    from photo_archiver.infrastructure.config import AppSettings

    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'stress.db'}")
    settings.ensure_runtime_directories()
    return bootstrap_application(settings)


def _run_scan(context, photos: Path):
    return context.services.scan_and_register_photos.execute(
        ScanAndRegisterPhotosCommand(folder_path=photos, recursive=True)
    )


def test_scan_stress_direct_service_2000_files(tmp_path: Path) -> None:
    """A 形态：纯服务链（无 Qt 线程）——基线，预期任何平台都稳定。"""
    context = _make_context(tmp_path)
    photos = _make_photo_tree(tmp_path, _FILE_COUNT)

    result = _run_scan(context, photos)

    assert result.registered_count == _FILE_COUNT
    assert result.failed_count == 0


def test_scan_stress_real_qthread_pool_2000_files(tmp_path: Path) -> None:
    """B 形态：真实 QThreadPool 跑扫描 worker，主线程 sleep 轮询（无 qtbot）。

    对应 LIMIT-006 的崩溃语境但剥离 qtbot——若此处段错误，qtbot 不是必要
    条件；若通过，D-3 嫌疑收敛到 qtbot 交互。
    """
    from PySide6.QtCore import QThreadPool

    from photo_archiver.workers.application_tasks import ScanAndRegisterPhotosTask

    context = _make_context(tmp_path)
    photos = _make_photo_tree(tmp_path, _FILE_COUNT)
    command = ScanAndRegisterPhotosCommand(folder_path=photos, recursive=True)
    task = ScanAndRegisterPhotosTask(context.services.scan_and_register_photos, command)

    done = threading.Event()
    captured: list = []
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            captured.append(task.run())
        except BaseException as error:  # noqa: BLE001 - the experiment must record crashes' Py-level echoes
            errors.append(error)
        finally:
            done.set()

    pool = QThreadPool.globalInstance()
    pool.start(_run)

    deadline = time.monotonic() + _TIMEOUT_SECONDS
    while not done.is_set():
        if time.monotonic() > deadline:
            pytest.fail(f"scan worker did not finish within {_TIMEOUT_SECONDS}s")
        time.sleep(0.1)

    assert not errors, f"worker raised: {errors!r}"
    result = captured[0]
    assert result.registered_count == _FILE_COUNT
    assert result.failed_count == 0
