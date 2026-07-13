"""Tests for worker task primitives and application task wrappers."""

from pathlib import Path

import pytest

from photo_archiver.application.commands import ImportPeopleCommand, ScanAndRegisterPhotosCommand
from photo_archiver.application.dtos import ImportPeopleResult, ScanAndRegisterPhotosResult
from photo_archiver.workers import (
    ImportPeopleTask,
    QtWorkerExecutor,
    TaskCancelled,
    ScanAndRegisterPhotosTask,
    TaskCompleted,
    TaskFailed,
    TaskProgress,
    TaskStarted,
    WorkerTask,
    WorkerTaskCancelled,
)


class SuccessfulTask(WorkerTask[str]):
    """Worker task used to verify lifecycle events."""

    def __init__(self) -> None:
        super().__init__("successful")

    def execute(self) -> str:
        self.report_progress("halfway", current=1, total=2)
        return "done"


class FailingTask(WorkerTask[None]):
    """Worker task used to verify failure events."""

    def __init__(self) -> None:
        super().__init__("failing")

    def execute(self) -> None:
        raise RuntimeError("boom")


class CancellableTask(WorkerTask[None]):
    """Worker task used to verify cooperative cancellation."""

    def __init__(self) -> None:
        super().__init__("cancellable")

    def execute(self) -> None:
        self.report_progress("before cancellation")
        self.raise_if_cancelled()


class FakeThreadPool:
    """Thread pool stub that records submitted runnables."""

    def __init__(self) -> None:
        self.runnables = []

    def start(self, runnable: object) -> None:
        self.runnables.append(runnable)


class ImportPeopleUseCaseStub:
    """Stub import use case for application worker tests."""

    def __init__(self, result: ImportPeopleResult) -> None:
        self.result = result
        self.commands: list[ImportPeopleCommand] = []

    def execute(self, command: ImportPeopleCommand) -> ImportPeopleResult:
        self.commands.append(command)
        return self.result


class ScanAndRegisterPhotosUseCaseStub:
    """Stub scan use case for application worker tests."""

    def __init__(self, result: ScanAndRegisterPhotosResult) -> None:
        self.result = result
        self.commands: list[ScanAndRegisterPhotosCommand] = []

    def execute(self, command: ScanAndRegisterPhotosCommand) -> ScanAndRegisterPhotosResult:
        self.commands.append(command)
        return self.result


def test_worker_task_emits_started_progress_and_completed_events() -> None:
    """A successful task emits lifecycle events in execution order."""
    task = SuccessfulTask()
    events = []
    task.subscribe(events.append)

    result = task.run()

    assert result == "done"
    assert [type(event) for event in events] == [TaskStarted, TaskProgress, TaskCompleted]
    assert events[0].task_name == "successful"
    assert events[1].message == "halfway"
    assert events[1].current == 1
    assert events[1].total == 2
    assert events[2].result == "done"


def test_worker_task_emits_failed_event_and_reraises_exception() -> None:
    """A failing task notifies subscribers and preserves the original exception."""
    task = FailingTask()
    events = []
    task.subscribe(events.append)

    with pytest.raises(RuntimeError, match="boom"):
        task.run()

    assert [type(event) for event in events] == [TaskStarted, TaskFailed]
    assert events[1].task_name == "failing"
    assert events[1].message == "boom"


def test_worker_task_supports_cooperative_cancellation() -> None:
    """A cancellable task emits a cancelled event and preserves cancellation state."""
    task = CancellableTask()
    events = []
    task.subscribe(events.append)

    task.cancel("user requested")

    with pytest.raises(WorkerTaskCancelled, match="user requested"):
        task.run()

    assert task.is_cancel_requested is True
    assert [type(event) for event in events] == [TaskStarted, TaskCancelled]
    assert events[1].reason == "user requested"


def test_import_people_task_delegates_to_use_case_and_reports_result() -> None:
    """ImportPeopleTask wraps the use case without adding business decisions."""
    command = ImportPeopleCommand(source_path=Path("people.txt"), has_header=False)
    result = ImportPeopleResult(imported_count=2, skipped_count=1, errors=("row 4: invalid",))
    use_case = ImportPeopleUseCaseStub(result)
    task = ImportPeopleTask(use_case, command)
    events = []
    task.subscribe(events.append)

    actual = task.run()

    assert actual is result
    assert use_case.commands == [command]
    assert [type(event) for event in events] == [
        TaskStarted,
        TaskProgress,
        TaskProgress,
        TaskCompleted,
    ]
    assert events[-2].current == 3
    assert events[-2].total == 4


def test_scan_and_register_photos_task_delegates_to_use_case_and_reports_result() -> None:
    """ScanAndRegisterPhotosTask wraps the use case and reports coarse progress."""
    command = ScanAndRegisterPhotosCommand(folder_path=Path("photos"), recursive=True)
    result = ScanAndRegisterPhotosResult(
        discovered_count=5,
        registered_count=3,
        skipped_count=1,
        failed_count=1,
    )
    use_case = ScanAndRegisterPhotosUseCaseStub(result)
    task = ScanAndRegisterPhotosTask(use_case, command)
    events = []
    task.subscribe(events.append)

    actual = task.run()

    assert actual is result
    assert use_case.commands == [command]
    assert [type(event) for event in events] == [
        TaskStarted,
        TaskProgress,
        TaskProgress,
        TaskCompleted,
    ]
    assert events[-2].current == 5
    assert events[-2].total == 5


def test_qt_worker_executor_submits_task_to_thread_pool() -> None:
    """QtWorkerExecutor delegates execution to the configured thread pool."""
    thread_pool = FakeThreadPool()
    task = SuccessfulTask()
    executor = QtWorkerExecutor(thread_pool)  # type: ignore[arg-type]

    runnable = executor.submit(task)

    assert thread_pool.runnables == [runnable]
    assert runnable.task is task


def test_qt_worker_runnable_cancel_requests_task_cancellation() -> None:
    """Qt worker handles forward cancellation requests to the wrapped task."""
    thread_pool = FakeThreadPool()
    task = SuccessfulTask()
    runnable = QtWorkerExecutor(thread_pool).submit(task)  # type: ignore[arg-type]

    runnable.cancel("stop")

    assert task.is_cancel_requested is True
    with pytest.raises(WorkerTaskCancelled, match="stop"):
        task.raise_if_cancelled()