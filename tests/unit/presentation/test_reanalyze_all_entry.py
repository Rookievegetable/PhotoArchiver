"""MainWindow UI wiring tests for the reanalyze-all maintenance entry (任务书 D1).

任务书 §3/D1：「运行人脸识别」主工具栏入口已退役（识别并入扫描）；全库
重新分析降级为数据工具维护入口 ``_on_reanalyze_all_clicked``，走既有
RecognitionRunController 全库路径（photo_ids=None + 全档范围）。本文件覆盖：
入口落位与命名、空库拒答、确认/取消分支、拒因上屏、终态刷新与 run 统计
摘要。控制器 ``start_run`` 以可控假 runnable（真实 Qt 信号）替身，无 Qt
线程、无模型 IO。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox, QToolBar

from photo_archiver.app import bootstrap_application
from photo_archiver.application.dtos.workspace import ModelAvailability, WorkspaceStatus
from photo_archiver.domain import FaceCountRange
from photo_archiver.domain.entities import RecognitionRun, RecognitionRunStats
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.main_window import MainWindow
from photo_archiver.workers.events import (
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)

TASK = "run_recognition"


def _make_runnable():
    """Build a controllable runnable with real Qt signals (smoke-test pattern)."""
    from PySide6.QtCore import QObject, Signal

    class Signals(QObject):
        started = Signal(object)
        progress = Signal(object)
        completed = Signal(object)
        failed = Signal(object)
        cancelled = Signal(object)

    class FakeRunnable:
        def __init__(self) -> None:
            self.signals = Signals()
            self.cancel_calls: list[str] = []

        def replay_pending_terminal(self) -> None:
            """Interface parity with QtWorkerRunnable (no-op: no terminal retained)."""

        def cancel(self, reason: str = "") -> None:
            """Record cooperative-cancellation requests for later assertions."""
            self.cancel_calls.append(reason)

    return FakeRunnable()


def _make_window(qtbot, tmp_path, monkeypatch, *, with_photo: bool = False) -> MainWindow:
    """Build a real MainWindow over a tmp SQLite context (smoke-test pattern)."""
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'reanalyze_ui.db'}",
        model_path=tmp_path / "missing-models",
    )
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    monkeypatch.setattr(
        context.services.workspace_readiness, "execute",
        Mock(return_value=WorkspaceStatus(
            has_persons=True, has_photos=True, pending_match_count=1,
            pending_review_count=0, archivable_count=1,
            archive_root_available=True,
            model_availability=ModelAvailability.AVAILABLE,
        )),
    )
    if with_photo:
        from photo_archiver.domain import Photo, PhotoPath

        context.repositories.photos.add(Photo(path=PhotoPath("photos/reanalyze.jpg")))
    window = MainWindow(context)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=0))
    monkeypatch.setattr(QMessageBox, "information", Mock(return_value=0))
    return window


def _stub_start(window, monkeypatch):
    """Replace start_run with a recorder returning a controllable fake runnable."""
    calls: list[tuple] = []
    runnable = _make_runnable()
    monkeypatch.setattr(
        window._recognition_run_controller, "start_run",
        lambda ranges, photo_ids=None: (
            calls.append((ranges, photo_ids)) or runnable
        ),
    )
    return calls, runnable


def _stub_confirm(monkeypatch, *, accepted: bool) -> None:
    """Double the QMessageBox confirm: exec returns Ok or Cancel."""
    monkeypatch.setattr(QMessageBox, "exec", lambda self: (
        QMessageBox.StandardButton.Ok if accepted
        else QMessageBox.StandardButton.Cancel
    ))


def test_maintenance_action_lives_on_data_tools_only(qtbot, tmp_path, monkeypatch) -> None:
    """任务书 D1：主工具栏无识别入口；维护入口在数据工具页且默认可用。"""
    window = _make_window(qtbot, tmp_path, monkeypatch)
    main = window.findChild(QToolBar, "Main")
    # Owner 2026-10-30：顶部固定入口栏撤除——主工具栏默认零动作（仅插件
    # 挂点），流程与维护入口都不再出现在这里。
    assert main.actions() == []
    assert main.isHidden()
    # 参考图基线：维护入口呈现为操作卡（QPushButton#ActionCard），QAction
    # 实例与处理器链零变化。
    from PySide6.QtWidgets import QPushButton

    cards = window.findChildren(QPushButton, "ActionCard")
    assert text.ACTION_REANALYZE_ALL in {card.text() for card in cards}
    assert window._reanalyze_all_action.isEnabled()


def test_empty_library_refuses_without_dialog_or_submission(
    qtbot, tmp_path, monkeypatch,
) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch)
    calls, _ = _stub_start(window, monkeypatch)
    confirm = Mock()
    monkeypatch.setattr(QMessageBox, "exec", confirm)

    window._on_reanalyze_all_clicked()

    assert text.REANALYZE_ALL_NONE in window._status_label.text()
    confirm.assert_not_called()
    assert calls == []


def test_confirm_submits_full_library_run_with_all_ranges(
    qtbot, tmp_path, monkeypatch,
) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch, with_photo=True)
    calls, _runnable = _stub_start(window, monkeypatch)
    _stub_confirm(monkeypatch, accepted=True)

    window._on_reanalyze_all_clicked()

    ranges, photo_ids = calls[0]
    assert ranges == (FaceCountRange(1, None),)
    assert photo_ids is None
    assert "人脸识别" in window._status_label.text()


def test_cancel_confirm_submits_nothing(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch, with_photo=True)
    calls, _ = _stub_start(window, monkeypatch)
    _stub_confirm(monkeypatch, accepted=False)

    window._on_reanalyze_all_clicked()

    assert calls == []


def test_refusal_surfaces_reason(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch, with_photo=True)
    monkeypatch.setattr(
        window._recognition_run_controller, "last_refusal_reason", "拒绝原因X",
    )
    monkeypatch.setattr(
        window._recognition_run_controller, "start_run", lambda ranges, photo_ids=None: None,
    )
    _stub_confirm(monkeypatch, accepted=True)

    window._on_reanalyze_all_clicked()

    assert "拒绝原因X" in window._status_label.text()


def test_terminal_releases_entry_and_completed_carries_run_stats(
    qtbot, tmp_path, monkeypatch,
) -> None:
    """终态释放维护入口；completed 附带 run 五计数摘要（AUDIT 2026-09-20）。"""
    window = _make_window(qtbot, tmp_path, monkeypatch, with_photo=True)
    _calls, runnable = _stub_start(window, monkeypatch)
    _stub_confirm(monkeypatch, accepted=True)
    window._on_reanalyze_all_clicked()
    photo_refreshed: list[str] = []
    monkeypatch.setattr(window, "_refresh_photo_list", lambda: photo_refreshed.append("p"))

    run = RecognitionRun(parameters={})
    run.start()
    run.complete(RecognitionRunStats(
        face_count=5, unreadable_count=2, no_face_count=1, error_count=1,
        in_scope_photo_count=3, out_of_scope_photo_count=2,
    ))
    runnable.signals.started.emit(TaskStarted(TASK, "t1"))
    runnable.signals.progress.emit(TaskProgress(TASK, "t1", message="m", current=1, total=2))
    runnable.signals.completed.emit(TaskCompleted(TASK, "t1", run))

    assert window._progress.value() == 100
    assert photo_refreshed == ["p"]
    status = window._status_label.text()
    assert "检出人脸 5 张" in status
    assert "无法读取 2 张" in status
    assert "无脸 1 张" in status
    assert "检测异常 1 张" in status
    assert "范围内 3 张 · 范围外 2 张" in status


def test_failed_terminal_surfaces_error(qtbot, tmp_path, monkeypatch) -> None:
    window = _make_window(qtbot, tmp_path, monkeypatch, with_photo=True)
    _calls, runnable = _stub_start(window, monkeypatch)
    _stub_confirm(monkeypatch, accepted=True)
    window._on_reanalyze_all_clicked()
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)

    runnable.signals.failed.emit(TaskFailed(TASK, ValueError("模型缺失")))

    # 具体失败信息走模态警告（状态栏只放任务级标签）。
    assert "模型缺失" in warning.call_args.args[-1]
    assert not window._task_coordinator.is_busy
