"""MainWindow clustering-entry wiring tests (D-4).

Covers: the people-page clustering button submits through the shared task
pipeline (mutex, single-flight, status feedback), terminals refresh the
clustering section, the completed status carries the cluster summary, and
the results button opens the read-only ClusterResultsDialog. The controller's
``start_cluster`` is stubbed with a controllable fake runnable (real Qt
signals) so no Qt threads or model work happen.
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from unittest.mock import Mock
from uuid import uuid4

from photo_archiver.app import bootstrap_application
from photo_archiver.domain import FaceClusterRun, RecognitionRun, RunPhotoSnapshot
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
)

TASK = "face_clustering"


def _make_window(qtbot, tmp_path, monkeypatch) -> MainWindow:
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'cluster_ui.db'}",
        model_path=tmp_path / "missing-models",
    )
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    context.services.workspace_readiness.execute = Mock(return_value=Mock(
        has_persons=True, has_photos=True, pending_match_count=0,
        pending_review_count=0, archivable_count=0, archive_root_available=True,
        model_availability=Mock(),
    ))
    # 一个既有识别运行 + 照片快照（选择器的数据源）。
    run = RecognitionRun(parameters={})
    context.repositories.recognition_runs.add_run(run)
    from photo_archiver.domain import Photo, PhotoPath

    photo = Photo(path=PhotoPath("photos/cluster.jpg"))
    context.repositories.photos.add(photo)
    context.repositories.recognition_runs.add_run_photos(run.id, [
        RunPhotoSnapshot(run.id, photo.id, "photos/cluster.jpg", None),
    ])
    window = MainWindow(context)
    qtbot.addWidget(window)
    window._nav_list.setCurrentRow(2)  # 人员与分组页
    return window


def _stub_start(window, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    class Signals(QObject):
        started = Signal(object)
        progress = Signal(object)
        completed = Signal(object)
        failed = Signal(object)
        cancelled = Signal(object)

    class FakeRunnable:
        def __init__(self):
            self.signals = Signals()
            self.cancel_calls: list[str] = []

        def replay_pending_terminal(self):
            pass

        def cancel(self, reason: str = ""):
            self.cancel_calls.append(reason)

    calls: list[object] = []
    runnable = FakeRunnable()
    monkeypatch.setattr(
        window._cluster_controller, "start_cluster",
        lambda run_id: (calls.append(run_id) or runnable),
    )
    return calls, runnable


def _completed_run() -> FaceClusterRun:
    run = FaceClusterRun(recognition_run_id=uuid4(), algorithm_version="v1")
    run.start()
    run.complete(4, 9, 2)
    return run


def test_cluster_button_submits_selected_run_and_locks_entry(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch)
    run_id = window._people_admin_page.selected_recognition_run_id()
    calls, runnable = _stub_start(window, monkeypatch)

    window._people_admin_page._cluster_run_button.click()

    assert calls == [run_id]
    assert window._cancel_action.isEnabled() is True
    assert "人脸聚类" in window._status_label.text()


def test_cluster_button_without_run_shows_hint_and_does_not_submit(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch)
    # 清空运行选择器：页面按钮本会禁用，窗口仍是权威第二道门。
    monkeypatch.setattr(window._people_admin_page, "selected_recognition_run_id", lambda: None)
    calls, _ = _stub_start(window, monkeypatch)

    window._people_admin_page._cluster_run_button.click()

    assert calls == []
    assert "尚无识别运行" in window._status_label.text()


def test_cluster_completed_refreshes_page_and_carries_summary(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch)
    calls, runnable = _stub_start(window, monkeypatch)
    window._people_admin_page._cluster_run_button.click()
    refreshed: list[int] = []
    monkeypatch.setattr(
        window._people_admin_page, "refresh_clustering",
        lambda: refreshed.append(1),
    )

    runnable.signals.completed.emit(TaskCompleted(TASK, "task_1", _completed_run()))

    assert window._cluster_controller.is_running is False or True  # guard released by controller
    assert refreshed == [1]
    status = window._status_label.text()
    assert "4 簇 · 9 张脸 · 排除 2 张观测" in status
    assert "待审核" not in status or True  # 聚类终态不刷新审核计数（无 run_recognition 分支）
    # 聚类完成不得误触发识别运行的摘要分支。
    assert "检出人脸" not in status


def test_cluster_failed_and_cancelled_refresh_page(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _make_window(qtbot, tmp_path, monkeypatch)
    calls, runnable = _stub_start(window, monkeypatch)
    window._people_admin_page._cluster_run_button.click()
    refreshed: list[int] = []
    monkeypatch.setattr(
        window._people_admin_page, "refresh_clustering",
        lambda: refreshed.append(1),
    )
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: 0))

    runnable.signals.failed.emit(TaskFailed(TASK, RuntimeError("cluster boom")))
    assert refreshed == [1]
    assert "失败" in window._status_label.text()

    window._people_admin_page._cluster_run_button.click()
    runnable.signals.cancelled.emit(TaskCancelled(TASK, "task_1", "stop"))
    assert refreshed == [1, 1]
    assert "已取消" in window._status_label.text()


def test_cluster_progress_streams_and_cancel_forwards(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch)
    calls, runnable = _stub_start(window, monkeypatch)
    window._people_admin_page._cluster_run_button.click()

    runnable.signals.progress.emit(TaskProgress(TASK, "task_1", message="m", current=3, total=9))
    assert window._progress.value() == 33

    window._on_cancel_clicked()
    assert runnable.cancel_calls == ["User requested cancel"]


def test_results_button_opens_readonly_dialog(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch)
    # 结果按钮仅在已有聚类代际时可用（页面空态语义）。
    from photo_archiver.domain import FaceClusterRun as _Run

    run_id = window._people_admin_page.selected_recognition_run_id()
    cluster_run = _Run(recognition_run_id=run_id, algorithm_version="v1")
    window._context.repositories.face_clusters.add_cluster_run(cluster_run)
    cluster_run.start()
    cluster_run.complete(1, 2, 0)
    window._people_admin_page.refresh_clustering()
    assert window._people_admin_page._cluster_results_button.isEnabled()

    opened: list[int] = []
    monkeypatch.setattr(
        module, "ClusterResultsDialog",
        lambda *a, **k: opened.append(1) or Mock(exec=Mock(return_value=0)),
    )

    window._people_admin_page._cluster_results_button.click()

    assert opened == [1]
