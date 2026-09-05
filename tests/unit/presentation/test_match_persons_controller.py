"""Tests for MatchPersonsController — precondition gating + single-flight guard.

Phase 4.2 / FEATURE-001 Commit 2. Covers:
- precondition refusals (no persons / no photos / all photos already matched)
- command construction submits only photos without recognition results
- single-flight guard (AC-014) and its auto-release on terminal signals
- connect_signals wiring of the task's five signals
"""

import pytest

pytest.importorskip("PySide6")

from uuid import UUID, uuid4

from photo_archiver.domain import Person, Photo, PhotoPath
from photo_archiver.presentation.controllers import MatchPersonsController
from photo_archiver.workers import QtWorkerRunnable


def _photo(name: str, photo_id: UUID | None) -> Photo:
    return Photo(path=PhotoPath(f"photos/{name}"), id=photo_id)


class _FakePeopleRepo:
    """Minimal PersonRepository stand-in: only list_all() is used."""

    def __init__(self, people=()):
        self._people = list(people)

    def list_all(self):
        return list(self._people)


class _FakePhotosRepo:
    """Minimal PhotoRepository stand-in: only list_all() is used."""

    def __init__(self, photos=()):
        self._photos = list(photos)

    def list_all(self):
        return list(self._photos)


class _FakeRecognitionRepo:
    """Reports an existing result per matched photo id, none otherwise."""

    def __init__(self, matched_ids=()):
        self._matched_ids = set(matched_ids)

    def list_first_by_photo_ids(self, photo_ids):
        return {pid: object() for pid in photo_ids if pid in self._matched_ids}


class _RecordingExecutor:
    """Wraps the submitted task in a real QtWorkerRunnable (so real signals are
    usable for guard-release tests) without starting any thread, and records
    the task + its command for assertions (mirrors the ArchiveController fake)."""

    def __init__(self) -> None:
        self.last_task = None
        self.last_command = None
        self.last_runnable: QtWorkerRunnable | None = None

    def submit(self, task):
        self.last_task = task
        # Peek once at submit time instead of reaching into _command later.
        self.last_command = getattr(task, "_command", None)
        runnable = QtWorkerRunnable(task)
        self.last_runnable = runnable
        return runnable


class _StubUseCase:
    """Carried inside the task; the controller must never call it directly."""

    def execute(self, command):  # pragma: no cover - guards against misuse
        raise AssertionError("controller must not execute the use case synchronously")


def _make_controller(people, photos, matched_ids=()):
    executor = _RecordingExecutor()
    controller = MatchPersonsController(
        photos=_FakePhotosRepo(photos),
        people=_FakePeopleRepo(people),
        recognition=_FakeRecognitionRepo(matched_ids),
        use_case=_StubUseCase(),
        executor=executor,
    )
    return controller, executor


def test_start_match_submits_only_photos_without_results() -> None:
    """Command carries only photo ids lacking a recognition result (resume semantics)."""
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    controller, executor = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", p1), _photo("b.jpg", p2), _photo("c.jpg", p3)],
        matched_ids={p2},
    )

    runnable = controller.start_match()

    assert runnable is not None
    assert executor.last_task is not None
    assert executor.last_command is not None
    assert executor.last_command.photo_ids == (p1, p3)
    assert len(executor.last_command.images) == 2


def test_start_match_refuses_when_no_persons_imported() -> None:
    controller, executor = _make_controller(people=[], photos=[_photo("a.jpg", uuid4())])

    assert controller.start_match() is None
    assert "尚未导入人员" in controller.last_refusal_reason
    assert executor.last_task is None


def test_start_match_refuses_when_no_photos_registered() -> None:
    controller, executor = _make_controller(people=[Person(name="Alice", id=uuid4())], photos=[])

    assert controller.start_match() is None
    assert "尚未登记照片" in controller.last_refusal_reason
    assert executor.last_task is None


def test_start_match_refuses_when_all_photos_already_matched() -> None:
    pid = uuid4()
    controller, executor = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", pid)],
        matched_ids={pid},
    )

    assert controller.start_match() is None
    assert "均已有识别结果" in controller.last_refusal_reason
    assert executor.last_task is None


def test_single_flight_guard_blocks_second_start() -> None:
    """AC-014: a second start while a task is in flight must be refused."""
    controller, executor = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", uuid4())],
    )

    first = controller.start_match()
    assert first is not None
    assert controller.is_running

    second = controller.start_match()
    assert second is None
    assert "正在进行" in controller.last_refusal_reason
    assert executor.last_runnable is first


def test_guard_released_on_completed_allows_next_batch() -> None:
    controller, _ = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", uuid4()), _photo("b.jpg", uuid4())],
    )
    runnable = controller.start_match()
    assert runnable is not None
    controller.connect_signals(
        runnable,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
    )

    runnable.signals.completed.emit(object())

    assert not controller.is_running
    assert controller.start_match() is not None


def test_guard_released_on_failed_allows_retry() -> None:
    controller, _ = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", uuid4())],
    )
    runnable = controller.start_match()
    assert runnable is not None
    controller.connect_signals(
        runnable,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
    )

    runnable.signals.failed.emit(RuntimeError("boom"))

    assert not controller.is_running


def test_guard_released_on_cancelled_allows_restart() -> None:
    controller, _ = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", uuid4())],
    )
    runnable = controller.start_match()
    assert runnable is not None
    controller.connect_signals(
        runnable,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        cancelled=lambda _e: None,
    )

    runnable.signals.cancelled.emit(object())

    assert not controller.is_running


def test_connect_signals_wires_all_five_channels() -> None:
    """Every task signal reaches the connected UI slot (completed also releases)."""
    controller, _ = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", uuid4())],
    )
    runnable = controller.start_match()
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
    """A late terminal from a superseded runnable must not clear the new guard."""
    controller, _ = _make_controller(
        people=[Person(name="Alice", id=uuid4())],
        photos=[_photo("a.jpg", uuid4()), _photo("b.jpg", uuid4())],
    )
    first = controller.start_match()
    assert first is not None
    controller.connect_signals(
        first,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
        lambda _e: None,
    )
    first.signals.cancelled.emit(object())
    second = controller.start_match()
    assert second is not None and second is not first

    first.signals.cancelled.emit(object())  # stale terminal re-emit

    assert controller.is_running  # second batch guard unaffected


