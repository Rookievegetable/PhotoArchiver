"""Tests for RecognitionRunController — 阶段 C Commit 3 新识别入口.

Covers command construction (whole library / selected re-analysis), the
immutable parameters snapshot, range passthrough, and the single-flight
guard. The controller deliberately has **no recognition-repository port**:
existing RecognitionResult rows must never trim or block a run (hard
constraint 6) — the assertions document that by submitting every photo.
"""

import pytest

pytest.importorskip("PySide6")

from pathlib import Path
from uuid import uuid4

from photo_archiver.domain import FaceCountRange, Photo, PhotoPath
from photo_archiver.presentation.controllers import RecognitionRunController
from photo_archiver.workers import QtWorkerRunnable


def _photo(photo_id):
    return Photo(path=PhotoPath(f"photos/{photo_id}.jpg"), id=photo_id)


class _FakePhotosRepo:
    """Minimal PhotoRepository stand-in: only list_all() is used."""

    def __init__(self, photos=()):
        self._photos = list(photos)

    def list_all(self):
        return list(self._photos)


class _RecordingExecutor:
    """Wrap the submitted task in a real QtWorkerRunnable without a thread."""

    def __init__(self) -> None:
        self.last_task = None
        self.last_command = None
        self.last_runnable: QtWorkerRunnable | None = None

    def submit(self, task):
        self.last_task = task
        self.last_command = getattr(task, "_command", None)
        runnable = QtWorkerRunnable(task)
        self.last_runnable = runnable
        return runnable


class _StubUseCase:
    """Carried inside the task; the controller must never call it directly."""

    def execute(self, command):  # pragma: no cover - guards against misuse
        raise AssertionError("controller must not execute the use case synchronously")


RANGES = (FaceCountRange(1, 1), FaceCountRange(2, 3))


def _make_controller(photos, use_case=_StubUseCase()):
    executor = _RecordingExecutor()
    controller = RecognitionRunController(
        photos=_FakePhotosRepo(photos), use_case=use_case, executor=executor,
    )
    return controller, executor


def test_start_run_submits_whole_library_with_parameters_snapshot() -> None:
    """photo_ids=None → 全库快照进入命令，parameters 记录范围与数量。"""
    p1, p2 = uuid4(), uuid4()
    controller, executor = _make_controller([_photo(p1), _photo(p2)])

    runnable = controller.start_run(RANGES)

    assert runnable is not None
    command = executor.last_command
    assert command.photo_ids == (p1, p2)
    assert command.images == (Path(f"photos/{p1}.jpg"), Path(f"photos/{p2}.jpg"))
    assert command.selected_ranges == RANGES
    assert dict(command.parameters) == {
        "photo_scope": "all",
        "photo_count": 2,
        "face_count_ranges": ["1", "2-3"],
    }


def test_start_run_reanalyzes_only_the_selection() -> None:
    """显式 photo_ids → 重新分析选中：命令只带选中照片，scope=selected。"""
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    controller, executor = _make_controller([_photo(p1), _photo(p2), _photo(p3)])

    controller.start_run(RANGES, photo_ids=(p1, p3))

    command = executor.last_command
    assert command.photo_ids == (p1, p3)
    assert dict(command.parameters)["photo_scope"] == "selected"
    assert dict(command.parameters)["photo_count"] == 2


def test_start_run_does_not_filter_already_matched_photos() -> None:
    """硬性约束 6：已有识别结果不阻止新检测 Run——控制器不读识别仓储，
    全部照片原样进入命令（对照旧 MatchPersonsController 的续跑语义）。"""
    pid = uuid4()
    controller, executor = _make_controller([_photo(pid)])

    controller.start_run(RANGES)

    assert executor.last_command.photo_ids == (pid,)


def test_start_run_refuses_when_model_pack_missing() -> None:
    """run_recognition 为 None（模型缺失）→ 拒绝并给出原因。"""
    controller, executor = _make_controller([_photo(uuid4())], use_case=None)

    assert controller.start_run(RANGES) is None
    assert "人脸识别不可用" in controller.last_refusal_reason
    assert executor.last_task is None


def test_start_run_refuses_when_no_photos_registered() -> None:
    controller, executor = _make_controller([])

    assert controller.start_run(RANGES) is None
    assert "尚未登记照片" in controller.last_refusal_reason
    assert executor.last_task is None


def test_start_run_refuses_empty_selection() -> None:
    """选中集为空（对话框本应阻止）→ 防御性拒绝，不提交空 Run。"""
    p1 = uuid4()
    controller, executor = _make_controller([_photo(p1)])

    assert controller.start_run(RANGES, photo_ids=()) is None
    assert "尚未登记照片" in controller.last_refusal_reason
    assert executor.last_task is None


def test_single_flight_guard_blocks_second_start() -> None:
    controller, executor = _make_controller([_photo(uuid4())])

    first = controller.start_run(RANGES)
    assert first is not None
    assert controller.is_running

    second = controller.start_run(RANGES)
    assert second is None
    assert "正在进行" in controller.last_refusal_reason
    assert executor.last_runnable is first


def test_guard_released_on_completed_allows_next_run() -> None:
    controller, _ = _make_controller([_photo(uuid4())])
    runnable = controller.start_run(RANGES)
    assert runnable is not None
    controller.connect_signals(
        runnable,
        lambda _e: None, lambda _e: None, lambda _e: None, lambda _e: None,
    )

    runnable.signals.completed.emit(object())

    assert not controller.is_running
    assert controller.start_run(RANGES) is not None


def test_guard_released_on_cancelled_and_failed() -> None:
    for signal_name in ("failed", "cancelled"):
        controller, _ = _make_controller([_photo(uuid4())])
        runnable = controller.start_run(RANGES)
        assert runnable is not None
        controller.connect_signals(
            runnable,
            lambda _e: None, lambda _e: None, lambda _e: None, lambda _e: None,
            cancelled=lambda _e: None,
        )
        getattr(runnable.signals, signal_name).emit(object())
        assert not controller.is_running


def test_connect_signals_wires_all_five_channels() -> None:
    controller, _ = _make_controller([_photo(uuid4())])
    runnable = controller.start_run(RANGES)
    assert runnable is not None
    received: list[str] = []
    controller.connect_signals(
        runnable,
        lambda _e: received.append("started"),
        lambda _e: received.append("progress"),
        lambda _e: received.append("completed"),
        lambda _e: received.append("failed"),
        cancelled=lambda _e: received.append("cancelled"),
    )

    runnable.signals.started.emit(object())
    runnable.signals.progress.emit(object())
    runnable.signals.failed.emit(object())
    runnable.signals.cancelled.emit(object())

    assert received == ["started", "progress", "failed", "cancelled"]


def test_terminal_from_stale_runnable_does_not_release_new_guard() -> None:
    controller, _ = _make_controller([_photo(uuid4()), _photo(uuid4())])
    first = controller.start_run(RANGES)
    assert first is not None
    controller.connect_signals(
        first, lambda _e: None, lambda _e: None, lambda _e: None, lambda _e: None,
    )
    first.signals.cancelled.emit(object())
    second = controller.start_run(RANGES)
    assert second is not None and second is not first

    first.signals.cancelled.emit(object())  # stale terminal re-emit

    assert controller.is_running  # second run guard unaffected
