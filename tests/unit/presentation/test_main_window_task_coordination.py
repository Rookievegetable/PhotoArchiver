"""Batch1 cross-task and synchronous-entry guards through the actual window."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFileDialog, QMessageBox

from photo_archiver.app import bootstrap_application
from photo_archiver.application.dtos.export import ExportScope
from photo_archiver.application.dtos.import_draft import ImportDraft
from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.domain import MatchStatus, PhotoSearchCriteria, RecognitionRun
from photo_archiver.domain.entities import ImportBatch, ImportDraftRow
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.ui_text import STATUS_CANCELLING, TASK_LABELS
from photo_archiver.presentation.views import main_window as module
from photo_archiver.presentation.views.import_preview_dialog import CONFIRM_SYNC_LIMIT
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskFailed, TaskProgress
from photo_archiver.workers.qt_executor import QtWorkerSignals


READY = WorkspaceStatus(
    has_persons=True, has_photos=True, pending_match_count=1,
    pending_review_count=0, archivable_count=1, archive_root_available=True,
    model_availability=ModelAvailability.AVAILABLE,
)


def _assert_persistent_actions_enabled(window) -> None:
    """The ready snapshot enables workflows, but deletion still needs selection."""
    assert not window._delete_photos_action.isEnabled()
    for action in window._conflicting_actions:
        if action is not window._delete_photos_action:
            assert action.isEnabled(), action.toolTip()


class Runnable:
    def __init__(self, pending=None):
        self.signals = QtWorkerSignals()
        self.pending = pending
        self.cancel_calls = []

    def cancel(self, reason=""):
        self.cancel_calls.append(reason)

    def replay_pending_terminal(self):
        event, self.pending = self.pending, None
        if isinstance(event, TaskCompleted):
            self.signals.completed.emit(event)
        elif isinstance(event, TaskCancelled):
            self.signals.cancelled.emit(event)
        elif isinstance(event, TaskFailed):
            self.signals.failed.emit(event)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'tasks.db'}",
        model_path=tmp_path / "missing-models",
    )
    context = bootstrap_application(settings)
    monkeypatch.setattr(context.services.workspace_readiness, "execute", Mock(return_value=READY))
    window = MainWindow(context)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    return window


def _stage_a_parse_and_dialog_doubles(window, monkeypatch):
    """Stage A two-stage doubles for the import entry.

    The parse service is faked to a persisted-looking draft with
    ``CONFIRM_SYNC_LIMIT + 1`` rows, so the window's confirm takes the Worker
    path (submission via ``worker_executor.submit``) — the point these tests
    stub. The preview dialog auto-accepts (same modal doubling policy as the
    export/archive dialogs above).
    """
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("people.txt", ""))
    batch = ImportBatch(file_name="people.txt", file_hash="stub", source_type="txt")
    rows = [
        ImportDraftRow(batch_id=batch.id, source_row=index, parsed_name=f"人员{index}")
        for index in range(1, CONFIRM_SYNC_LIMIT + 2)
    ]
    draft = ImportDraft(batch=batch, rows=rows, header=None, field_mapping={"name": 0})
    monkeypatch.setattr(
        window._context.services.parse_import_draft, "execute", lambda command: draft,
    )
    monkeypatch.setattr(
        module, "ImportPreviewDialog",
        lambda *a, **k: SimpleNamespace(
            exec=lambda: 1, batch_id=batch.id, row_count=len(rows),
        ),
    )


def prepare(window, monkeypatch, tmp_path, name, runnable):
    """Use real controller wiring, stub only submission/preparation."""
    dialog = SimpleNamespace(
        exec=lambda: 1, output_path=tmp_path / "out.csv", scope=ExportScope.ALL,
        format_name="csv", conflict_strategy="skip", dry_run=False,
    )
    if name == "import_people":
        # Stage A: parse/dialog doubled; confirm (>CONFIRM_SYNC_LIMIT rows)
        # submits ConfirmImportTask through the shared worker executor.
        _stage_a_parse_and_dialog_doubles(window, monkeypatch)
        controller, method, entry = window._context.worker_executor, "submit", "import"
    elif name == "scan_photos":
        # 任务书 §3 A1：扫描入口提交组合任务（登记+特征），控制器接口不变。
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
        controller, method, entry = window._scan_controller, "scan_folder", "scan"
    elif name == "face_clustering":
        # D-4 + 任务书 D2：入口先弹聚类范围对话框（桩为默认选择），随后提交经
        # ClusterFacesController.start_cluster（library 数据集）。
        monkeypatch.setattr(module, "ClusterRangeDialog", lambda *a, **k: SimpleNamespace(
            exec=lambda: 1, selected_ranges=(),
        ))
        run = RecognitionRun(parameters={})
        window._context.repositories.recognition_runs.add_run(run)
        window._people_admin_page.refresh_clustering()
        controller, method, entry = window._cluster_controller, "start_cluster", "cluster_run"
    elif name == "archive_photos":
        monkeypatch.setattr(window, "_effective_archive_root", lambda: tmp_path)
        monkeypatch.setattr(window._archive_controller, "preview",
                            lambda *a, **k: SimpleNamespace(planned_count=1))
        monkeypatch.setattr(module, "ArchivePreviewDialog", lambda *a, **k: dialog)
        controller, method, entry = window._archive_controller, "execute", "archive"
    else:
        monkeypatch.setattr(module, "ExportDialog", lambda *a, **k: dialog)
        controller, method, entry = window._export_controller, "export", "export"
    submit = Mock(return_value=runnable)
    monkeypatch.setattr(controller, method, submit)
    return getattr(window, f"_on_{entry}_clicked"), submit


# 任务书 D1/§3：match_persons 早已退役；run_recognition 降级为数据工具维护
# 入口（不在主链参数化内）；scan_and_register_photos 更名为 scan_photos。
# pairing_batch（批量终审）＝聚类结果对话框级任务：经同一 TaskCoordinator
# 准入（对话框注入），但无窗口级入口——不在本窗口参数化内（对话框端到端
# 准入/进度/终态由 test_cluster_pairing_dialog 的异步用例覆盖）。
_WINDOW_TASK_NAMES = [
    n for n in TASK_LABELS
    if n not in ("import_confirm", "match_persons", "run_recognition",
                 "scan_and_register_photos", "pairing_batch")
]


@pytest.mark.parametrize("name", _WINDOW_TASK_NAMES)
def test_five_tasks_block_every_conflicting_entry_and_cancel_correctly(
    window, monkeypatch, tmp_path, name,
):
    runnable = Runnable()
    entry, submit = prepare(window, monkeypatch, tmp_path, name, runnable)
    original = [(a.isEnabled(), a.toolTip()) for a in window._conflicting_actions]
    entry()
    assert submit.call_count == 1
    for action in window._conflicting_actions:
        assert not action.isEnabled()
        assert TASK_LABELS[name] in action.toolTip()
    for other in ("import", "scan", "archive", "export", "review", "settings",
                  "detect_duplicates", "delete_photos", "delete_person"):
        getattr(window, f"_on_{other}_clicked")()  # bypass disabled QAction
    window._on_plugin_action("anything")
    assert submit.call_count == 1
    window._on_cancel_clicked()
    window._on_cancel_clicked()
    assert runnable.cancel_calls == ["User requested cancel"]
    assert window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    runnable.signals.progress.emit(TaskProgress(name, current=2, total=8, message="working"))
    assert "25%" in window._status_label.text()
    assert "working" in window._status_label.text()
    assert STATUS_CANCELLING in window._status_label.text()
    runnable.signals.progress.emit(TaskProgress(name, current=3, total=0, message="unknown"))
    assert window._progress.maximum() == 0
    assert "%" not in window._status_label.text()
    assert STATUS_CANCELLING in window._status_label.text()
    runnable.signals.cancelled.emit(TaskCancelled(name))
    assert not window._task_coordinator.is_busy
    assert [(a.isEnabled(), a.toolTip()) for a in window._conflicting_actions] == original


@pytest.mark.parametrize("name", _WINDOW_TASK_NAMES)
@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_all_early_terminals_release_and_refresh_once(window, monkeypatch, tmp_path, name, kind):
    event = {"completed": TaskCompleted(name), "failed": TaskFailed(name, ValueError("bad")),
             "cancelled": TaskCancelled(name)}[kind]
    runnable = Runnable(event)
    entry, _ = prepare(window, monkeypatch, tmp_path, name, runnable)
    refresh = Mock()
    monkeypatch.setattr(window, "_refresh_photo_list", refresh)
    entry()
    getattr(runnable.signals, kind).emit(event)
    assert refresh.call_count == 1
    assert not window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    _assert_persistent_actions_enabled(window)


def test_double_import_during_picker_and_submission_is_reserved(window, monkeypatch, tmp_path):
    runnable = Runnable()
    entry, submit = prepare(window, monkeypatch, tmp_path, "import_people", runnable)

    def picker(*args):
        loop = QEventLoop()
        QTimer.singleShot(0, lambda: (entry(), window._on_export_clicked(), loop.quit()))
        loop.exec()
        assert not window._cancel_action.isEnabled()
        return "people.txt", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", picker)

    def submission(*args):
        entry()
        window._on_scan_clicked()  # 忙态下被准入拦截（任务书 D1：match 入口已退役）
        return runnable

    submit.side_effect = submission
    entry()
    entry()
    assert submit.call_count == 1


@pytest.mark.parametrize("path", ["settings", "detect_duplicates", "delete_photos",
                                  "delete_person", "plugin"])
def test_sync_modal_path_blocks_reentrant_task(window, monkeypatch, path):
    start = Mock()
    # 忙态下 @_exclusive 在对话框之前拦截；start_run 桩仅用于断言维护入口
    # （任务书 D1）忙时不触达识别控制器。
    # 2026-10-01 页面化：review 不再是同步模态路径（改为常驻页 + set_busy
    # 置灰，准入覆盖见 test_main_window_workspace_state 路由测试），从本
    # 参数化中移除。
    monkeypatch.setattr(window._recognition_run_controller, "start_run", start)

    def nested(*args, **kwargs):
        loop = QEventLoop()
        QTimer.singleShot(0, lambda: (window._on_scan_clicked(), loop.quit()))
        loop.exec()
        assert window._task_coordinator.is_busy
        return 0

    dialog = SimpleNamespace(exec=nested)
    if path == "settings":
        monkeypatch.setattr(module, "SettingsDialog", lambda *a: dialog)
    elif path == "delete_person":
        monkeypatch.setattr(module, "PersonDeletionDialog", lambda *a, **k: dialog)
    elif path == "delete_photos":
        monkeypatch.setattr(window, "_collect_selected_photo_ids", lambda: ())
        monkeypatch.setattr(QMessageBox, "information", nested)
    elif path == "detect_duplicates":
        monkeypatch.setattr(window._context.detect_duplicates_controller, "detect_and_show", nested)
    else:
        plugin = SimpleNamespace(actions=lambda: [SimpleNamespace(id="test")],
                                 execute_action=nested)
        monkeypatch.setattr(window._plugin_registry, "_enabled", {"test": plugin}, raising=False)
        # Registry's public enabled_plugins property is the host dispatch surface.
        monkeypatch.setattr(type(window._plugin_registry), "enabled_plugins",
                            property(lambda self: {"test": plugin}))
    if path == "plugin":
        window._on_plugin_action("test")
    else:
        getattr(window, f"_on_{path}_clicked")()
    start.assert_not_called()
    assert not window._task_coordinator.is_busy


def test_failed_retry_stale_events_and_previous_action_state(window, monkeypatch, tmp_path):
    old = Runnable()
    entry, submit = prepare(window, monkeypatch, tmp_path, "import_people", old)
    action = window._export_action
    action.setEnabled(False)
    action.setToolTip("previous reason")
    entry()
    old.signals.failed.emit(TaskFailed("import_people", ValueError("bad")))
    assert not action.isEnabled()
    assert action.toolTip() == "previous reason"
    fresh = Runnable()
    submit.return_value = fresh
    entry()
    status = window._status_label.text()
    old.signals.completed.emit(TaskCompleted("import_people"))
    old.signals.progress.emit(TaskProgress("import_people", message="stale"))
    assert window._active_runnable is fresh
    assert window._status_label.text() == status
    window._on_cancel_clicked()
    assert not old.cancel_calls
    assert fresh.cancel_calls == ["User requested cancel"]


@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_terminal_refresh_keeps_latest_criteria_and_partial_results(
    window, monkeypatch, tmp_path, kind,
):
    runnable = Runnable()
    entry, _ = prepare(window, monkeypatch, tmp_path, "import_people", runnable)
    entry()
    criteria = PhotoSearchCriteria(match_status=MatchStatus.PENDING)
    window._on_filter_changed(criteria)
    search = Mock(return_value=[])
    all_photos = Mock(return_value=[])
    catalog = Mock(return_value=[])
    monkeypatch.setattr(window._photo_list_controller, "search_photos", search)
    monkeypatch.setattr(window._photo_list_controller, "list_photos", all_photos)
    monkeypatch.setattr(window._context.services.list_persons, "execute", catalog)
    event = {"completed": TaskCompleted("import_people"),
             "failed": TaskFailed("import_people", ValueError("partial")),
             "cancelled": TaskCancelled("import_people")}[kind]
    getattr(runnable.signals, kind).emit(event)
    # 首次调用 = 列表刷新（criteria 快照）；其后 4 次 = 状态计数回填
    # （参考图 M8：状态复选框带计数，DEC-06 按图推翻——逐状态 push-down 查询）。
    assert search.call_args_list[0] == call(criteria)
    assert search.call_count == 5
    # 1 次 = 页头全库统计回填（参考图 M2：共 N 张照片 · M 人；只读 list_all）。
    all_photos.assert_called_once()
    # 2 次 = 筛选人员轴刷新 + 页头人员统计（均为只读 list_persons）。
    assert catalog.call_count == 2
    assert window._current_criteria is criteria


def test_cancel_exception_restores_retry_without_false_cancellation(window, monkeypatch, tmp_path):
    runnable = Runnable()
    entry, _ = prepare(window, monkeypatch, tmp_path, "import_people", runnable)
    entry()
    monkeypatch.setattr(runnable, "cancel", Mock(side_effect=RuntimeError("cancel failed")))
    window._on_cancel_clicked()
    assert window._active_runnable is runnable
    assert window._cancel_action.isEnabled()
    assert STATUS_CANCELLING not in window._status_label.text()
    assert "取消请求未能发送" in window._status_label.text()
    assert all(not a.isEnabled() for a in window._conflicting_actions)
    monkeypatch.setattr(runnable, "cancel", lambda reason: runnable.cancel_calls.append(reason))
    window._on_cancel_clicked()
    assert runnable.cancel_calls == ["User requested cancel"]
    assert STATUS_CANCELLING in window._status_label.text()
    runnable.signals.cancelled.emit(TaskCancelled("import_people"))
    assert not window._task_coordinator.is_busy


@pytest.mark.parametrize("kind", ["completed", "failed", "cancelled"])
def test_refresh_exception_releases_actions_and_preserves_failure_dialog(
    window, monkeypatch, tmp_path, kind,
):
    runnable = Runnable()
    entry, _ = prepare(window, monkeypatch, tmp_path, "import_people", runnable)
    entry()
    monkeypatch.setattr(window, "_refresh_photo_list", Mock(side_effect=OSError("database unavailable")))
    event = {"completed": TaskCompleted("import_people"),
             "failed": TaskFailed("import_people", RuntimeError("original worker error")),
             "cancelled": TaskCancelled("import_people")}[kind]
    getattr(runnable.signals, kind).emit(event)
    assert not window._task_coordinator.is_busy
    _assert_persistent_actions_enabled(window)
    assert "页面刷新失败" in window._status_label.text()
    if kind == "failed":
        assert QMessageBox.warning.call_args.args[2] == "original worker error"


def test_submission_exception_releases_reservation(window, monkeypatch, tmp_path):
    entry, submit = prepare(window, monkeypatch, tmp_path, "import_people", Runnable())
    submit.side_effect = OSError("unavailable")
    entry()
    assert not window._task_coordinator.is_busy
    assert not window._cancel_action.isEnabled()
    _assert_persistent_actions_enabled(window)


def test_pairing_batch_uses_dedicated_pool_isolated_from_global(window) -> None:
    """Owner 2026-10-31「卡住 0%」根因：批量终审与照片墙缩略图管线共用全局
    QThreadPool——缩略图刷新重排数百任务时批量 runnable 饥饿（0%、无日志、
    协调器被占）。专用单线程池＝与缩略图饥饿彻底隔离。"""
    from photo_archiver.workers.qt_executor import QtWorkerExecutor

    executor = getattr(window, "_pairing_batch_executor", None)
    assert isinstance(executor, QtWorkerExecutor)
    assert executor.thread_pool is not QThreadPool.globalInstance()


def test_cluster_results_dialog_open_does_not_reserve(
    window, qtbot, tmp_path, monkeypatch,
) -> None:
    """Owner 2026-10-31「已有批量终审在执行」全链根因：_on_cluster_results_clicked
    曾 @_exclusive 占位——模态对话框存活期间预留永不释放，对话框内批量准入
    全部被拒。修复后：打开不占位（协调器保持空闲），批量准入在对话框内完成。"""
    # 最小聚类种子：识别运行 + 1 簇（1 观测）+ 建议行，让对话框可打开。
    from photo_archiver.domain import (
        FaceBox,
        FaceCluster,
        FaceClusterMember,
        FaceClusterRun,
        FaceEmbedding,
        FaceObservation,
        Photo,
        PhotoPath,
        PhotoPathBase,
        RecognitionRun,
    )
    from photo_archiver.domain.entities.cluster_assignment import (
        ClusterPersonAssignment,
    )

    repos = window._context.repositories
    run = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="v1")
    repos.face_clusters.add_cluster_run(cluster_run)
    person = window._context.services.manage_people.add_person(
        __import__(
            "photo_archiver.application.commands", fromlist=["AddPersonCommand"],
        ).AddPersonCommand(name="甲", identity="E900"),
    )
    photo_file = tmp_path / "seed.jpg"
    photo_file.write_bytes(b"x")
    photo = Photo(
        path=PhotoPath(photo_file, base=PhotoPathBase.ABSOLUTE),
        original_name="seed.jpg",
    )
    repos.photos.add(photo)
    observation = FaceObservation(
        run_id=run.id,
        photo_id=photo.id,
        face_index=0,
        photo_face_count=1,
        det_score=0.9,
        box=FaceBox(0, 0, 10, 10),
        embedding=FaceEmbedding((0.1, 0.2)),
        scope_verdict="in_selected_scope",
    )
    repos.face_observations.add_many([observation])
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id,
        run_id=run.id,
        ordinal=0,
        member_count=1,
        sort_key="k|0000",
    )
    repos.face_clusters.add_clusters([cluster])
    repos.face_clusters.add_members([
        FaceClusterMember(
            cluster_id=cluster.id, observation_id=observation.id, confidence=0.9,
        ),
    ])
    cluster_run.start()
    cluster_run.complete(1, 1, 0)
    repos.face_clusters.update_cluster_run(cluster_run)
    repos.cluster_assignments.add_assignments([
        ClusterPersonAssignment(
            cluster_id=cluster.id,
            person_id=person.id,
            source="ordered_suggestion",
        ),
    ])
    window._people_admin_page.refresh()
    import photo_archiver.presentation.views.cluster_results_dialog as crd

    real_exec = crd.ClusterResultsDialog.exec
    captured = {}
    crd.ClusterResultsDialog.exec = lambda self: (captured.update(dialog=self), 1)[1]
    try:
        window._on_cluster_results_clicked()
    finally:
        crd.ClusterResultsDialog.exec = real_exec
    assert not window._task_coordinator.is_busy  # 打开不占位（修复点）
    dialog = captured.get("dialog")
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.show()
    # 预演弹窗自动 Ok（真实模态链不阻塞测试）。
    monkeypatch.setattr(
        "photo_archiver.presentation.views.cluster_results_dialog.QMessageBox.exec",
        lambda self: QMessageBox.StandardButton.Ok,
    )
    # 对话框内批量准入现在可达：选区 → 点击 → 协调器 admit。
    dialog._cluster_list.selectAll()
    if dialog._batch_pass_button.isEnabled():
        dialog._on_batch_pass_clicked()
        assert window._task_coordinator.is_busy  # 批量准入占位（正确语义）
        window._task_coordinator.cancel()  # 清场：协作式取消
        qtbot.waitUntil(lambda: not window._task_coordinator.is_busy, timeout=30000)
