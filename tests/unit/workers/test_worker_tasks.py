"""Tests for worker task primitives and application task wrappers."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from loguru import logger

from photo_archiver.application.commands import (
    ImportPeopleCommand,
    MatchPersonsCommand,
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.dtos import (
    ImportPeopleResult,
    MatchResult,
    ScanAndRegisterPhotosResult,
)
from photo_archiver.application.ports import ProgressReporter
from photo_archiver.workers import (
    ImportPeopleTask,
    MatchPersonsTask,
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


def test_worker_task_generates_unique_task_id_and_binds_to_logger() -> None:
    """WorkerTask.__init__ builds ``{name}_{uuid_hex[:8]}`` and emits it on every event.

    Covers ISSUE-002: structured telemetry requires a per-run identifier so
    concurrent same-type tasks remain distinguishable in logs and UI handlers.
    The id propagates to Started / Progress / Completed / Failed / Cancelled
    events and is bound to the Loguru context for the whole run.
    """
    task = SuccessfulTask()
    assert task.task_id.startswith("successful_")
    assert len(task.task_id) == len("successful_") + 8

    events = []
    task.subscribe(events.append)

    captured: list[dict] = []
    sink_id = logger.add(lambda message: captured.append(message.record))
    try:
        result = task.run()
    finally:
        logger.remove(sink_id)

    assert result == "done"
    assert [type(event) for event in events] == [TaskStarted, TaskProgress, TaskCompleted]
    for event in events:
        assert event.task_id == task.task_id


def test_logger_contextualize_binds_task_id_during_run() -> None:
    """Loguru ``contextualize`` injects task_id into ``record["extra"]`` so downstream
    Application service logs inherit the run identifier (ISSUE-002 core mechanism).

    Uses a task that itself emits a log line inside ``execute`` so the sink can
    observe the bound extra.
    """

    class LoggingTask(WorkerTask[None]):
        def __init__(self) -> None:
            super().__init__("logging")

        def execute(self) -> None:
            logger.info("inside execute")

    task = LoggingTask()
    captured: list[dict] = []
    sink_id = logger.add(lambda message: captured.append(message.record))
    try:
        task.run()
    finally:
        logger.remove(sink_id)

    assert any(record["extra"].get("task_id") == task.task_id for record in captured)


def test_two_same_type_tasks_have_distinct_task_ids() -> None:
    """Two instances of the same task type get different task_ids (concurrent runs)."""
    first = SuccessfulTask()
    second = SuccessfulTask()
    assert first.task_id != second.task_id
    assert first.task_id.startswith("successful_")
    assert second.task_id.startswith("successful_")


def test_failing_task_propagates_task_id_on_failed_event() -> None:
    """TaskFailed carries the task_id so UI/logs can correlate failures."""
    task = FailingTask()
    events = []
    task.subscribe(events.append)

    with pytest.raises(RuntimeError, match="boom"):
        task.run()

    assert [type(event) for event in events] == [TaskStarted, TaskFailed]
    assert events[0].task_id == task.task_id
    assert events[1].task_id == task.task_id


def test_cancelled_task_propagates_task_id_on_cancelled_event() -> None:
    """TaskCancelled carries the task_id."""
    task = CancellableTask()
    events = []
    task.subscribe(events.append)
    task.cancel("user requested")

    with pytest.raises(WorkerTaskCancelled, match="user requested"):
        task.run()

    assert [type(event) for event in events] == [TaskStarted, TaskCancelled]
    assert events[1].task_id == task.task_id


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


class MatchPersonsUseCaseStub:
    """Stub match use case exposing the ``bind_progress_reporter`` capability.

    Mirrors the real ``MatchPersonsService`` binding contract: the reporter is
    temporarily bound during ``execute`` and restored afterwards, and progress
    is streamed through the bound reporter's ``report`` adapter.
    """

    def __init__(self, results: tuple[MatchResult, ...]) -> None:
        self.results = results
        self.commands: list[MatchPersonsCommand] = []
        self.reporter_during_execute: list[ProgressReporter] = []
        self._reporter: ProgressReporter | None = None

    @property
    def current_reporter(self) -> ProgressReporter | None:
        """Expose the reporter currently bound (restoration assertions)."""
        return self._reporter

    def bind_progress_reporter(
        self, reporter: ProgressReporter
    ) -> AbstractContextManager[None]:
        """Temporarily bind ``reporter`` for the duration of one execute."""
        return _temporary_reporter_binding(self, reporter)

    def execute(self, command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
        self.commands.append(command)
        assert self._reporter is not None, "task must bind itself before execute"
        self.reporter_during_execute.append(self._reporter)
        if self.results:
            self._reporter.report(1, len(self.results), "Matched photo X")
        return self.results


@contextmanager
def _temporary_reporter_binding(
    stub: MatchPersonsUseCaseStub, reporter: ProgressReporter
) -> Iterator[None]:
    previous = stub._reporter
    stub._reporter = reporter
    try:
        yield
    finally:
        stub._reporter = previous


class BareMatchPersonsUseCaseStub:
    """Stub match use case WITHOUT the binder capability (sniff fallback path)."""

    def __init__(self, results: tuple[MatchResult, ...]) -> None:
        self.results = results
        self.commands: list[MatchPersonsCommand] = []

    def execute(self, command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
        self.commands.append(command)
        return self.results


class ExplodingMatchPersonsUseCaseStub(MatchPersonsUseCaseStub):
    """Stub whose execute raises — verifies failure propagation + binder restore."""

    def execute(self, command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
        self.commands.append(command)
        raise RuntimeError("model exploded")


class MidBatchCancelMatchPersonsUseCaseStub(MatchPersonsUseCaseStub):
    """Stub that cancels its task mid-execute (simulates user cancel during batch).

    The task reference is late-bound (assigned after construction) because the
    task itself needs the stub in its constructor.
    """

    task: object | None = None

    def execute(self, command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
        self.commands.append(command)
        assert self.task is not None, "test must late-bind the task"
        self.task.cancel("user stopped mid-batch")  # type: ignore[attr-defined]
        return self.results


def _match_command(count: int = 2) -> MatchPersonsCommand:
    return MatchPersonsCommand(
        photo_ids=tuple(uuid4() for _ in range(count)),
        images=tuple(Path(f"photo_{i}.jpg") for i in range(count)),
    )


def _match_results(command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
    return tuple(MatchResult(photo_id=pid) for pid in command.photo_ids)


def test_match_persons_task_binds_reporter_and_returns_service_results() -> None:
    """Normal path: bind task as reporter, forward command, pass results through.

    The reporter must be bound *during* execute (so service progress reaches the
    task event bus) and restored afterwards, and the service return value is
    returned verbatim — the task adds no business decisions.
    """
    command = _match_command(2)
    results = _match_results(command)
    use_case = MatchPersonsUseCaseStub(results)
    task = MatchPersonsTask(use_case, command)  # type: ignore[arg-type]
    events = []
    task.subscribe(events.append)

    actual = task.run()

    assert actual is results
    assert use_case.commands == [command]
    # Reporter was the task itself during execute (progress adapter wired).
    assert use_case.reporter_during_execute == [task]
    # Binding is temporary — restored after the run.
    assert use_case.current_reporter is None
    # Coarse task markers + the service-driven per-photo progress.
    assert [type(event) for event in events] == [
        TaskStarted,
        TaskProgress,
        TaskProgress,
        TaskProgress,
        TaskCompleted,
    ]
    assert events[1].message == "Matching faces"
    # Service-reported progress surfaced verbatim through the task adapter.
    assert events[2].current == 1
    assert events[2].total == 2
    assert events[2].message == "Matched photo X"
    assert events[3].message == "Face matching finished"
    assert events[3].current == 2
    assert events[3].total == 2


def test_match_persons_task_restores_previous_reporter_after_execute() -> None:
    """A pre-existing reporter binding is restored after the task finishes."""
    command = _match_command(1)
    use_case = MatchPersonsUseCaseStub(_match_results(command))
    sentinel = object()
    use_case._reporter = sentinel
    task = MatchPersonsTask(use_case, command)  # type: ignore[arg-type]

    task.run()

    assert use_case.current_reporter is sentinel


def test_match_persons_task_falls_back_when_service_lacks_binder() -> None:
    """Services without ``bind_progress_reporter`` still execute (getattr sniff)."""
    command = _match_command(1)
    results = _match_results(command)
    use_case = BareMatchPersonsUseCaseStub(results)
    task = MatchPersonsTask(use_case, command)  # type: ignore[arg-type]

    actual = task.run()

    assert actual is results
    assert use_case.commands == [command]


def test_match_persons_task_propagates_service_exception_as_failure() -> None:
    """Service exceptions surface as TaskFailed and restore the reporter binding."""
    command = _match_command(2)
    use_case = ExplodingMatchPersonsUseCaseStub(())
    task = MatchPersonsTask(use_case, command)  # type: ignore[arg-type]
    events = []
    task.subscribe(events.append)

    with pytest.raises(RuntimeError, match="model exploded"):
        task.run()

    assert use_case.commands == [command]
    # Coarse "Matching faces" marker was emitted before the service blew up.
    assert [type(event) for event in events] == [TaskStarted, TaskProgress, TaskFailed]
    assert events[1].message == "Matching faces"
    assert events[2].message == "model exploded"
    assert use_case.current_reporter is None


def test_match_persons_task_reports_cancellation_not_failure() -> None:
    """WorkerTaskCancelled raised inside the service is never swallowed as failure.

    This is the Task-level half of the cancellation contract: the real service
    re-raises ``WorkerTaskCancelled`` ahead of its broad per-photo handler, so
    a mid-batch user cancel must surface as TaskCancelled — never TaskFailed.
    """
    command = _match_command(3)

    class CancelFromReporterStub(MatchPersonsUseCaseStub):
        """Simulates the real service: reporter-driven cancel re-raised."""

        def execute(self, command: MatchPersonsCommand) -> tuple[MatchResult, ...]:
            self.commands.append(command)
            assert self._reporter is not None, "task must bind itself before execute"
            self._reporter.report(1, 3, "first photo")
            raise WorkerTaskCancelled("user stopped recognition")

    use_case = CancelFromReporterStub(_match_results(command))
    task = MatchPersonsTask(use_case, command)  # type: ignore[arg-type]
    events = []
    task.subscribe(events.append)

    with pytest.raises(WorkerTaskCancelled, match="user stopped recognition"):
        task.run()

    assert [type(event) for event in events] == [
        TaskStarted,
        TaskProgress,
        TaskProgress,
        TaskCancelled,
    ]
    assert events[-1].reason == "user stopped recognition"


def test_match_persons_task_skips_service_when_cancelled_before_run() -> None:
    """Cancellation requested before run() never reaches the service."""
    command = _match_command(2)
    use_case = MatchPersonsUseCaseStub(_match_results(command))
    task = MatchPersonsTask(use_case, command)  # type: ignore[arg-type]
    events = []
    task.subscribe(events.append)
    task.cancel("no longer needed")

    with pytest.raises(WorkerTaskCancelled, match="no longer needed"):
        task.run()

    assert use_case.commands == []
    assert [type(event) for event in events] == [TaskStarted, TaskCancelled]


def test_match_persons_task_detects_mid_batch_cancellation() -> None:
    """Cancel during execute: run() discards results and reports TaskCancelled."""
    command = _match_command(2)
    results = _match_results(command)
    cancellable = MidBatchCancelMatchPersonsUseCaseStub(results)
    task = MatchPersonsTask(cancellable, command)  # type: ignore[arg-type]
    cancellable.task = task
    events = []
    task.subscribe(events.append)

    with pytest.raises(WorkerTaskCancelled, match="user stopped mid-batch"):
        task.run()

    assert cancellable.commands == [command]
    assert [type(event) for event in events] == [TaskStarted, TaskProgress, TaskCancelled]
    assert events[-1].reason == "user stopped mid-batch"


def test_replay_pending_terminal_rescues_fast_fail_before_wiring() -> None:
    """macOS CI race (v2.3.0 acceptance): a task that terminates between
    submit() and the view's connect_signals() loses its terminal event —
    zero receivers were connected at emit time and the UI never re-enabled.

    Run the runnable synchronously (terminal reached, nothing connected),
    THEN connect a subscriber and replay: the late subscriber must receive
    the retained TaskFailed.
    """
    from photo_archiver.workers.events import TaskFailed
    from photo_archiver.workers.qt_executor import QtWorkerRunnable

    class _FailingTask(WorkerTask[object]):
        def __init__(self) -> None:
            super().__init__("instant_fail")

        def execute(self) -> object:
            raise ValueError("boom before any subscriber connected")

    task = _FailingTask()
    runnable = QtWorkerRunnable(task)  # noqa: SLF001 - constructor is public via executor
    runnable.run()  # terminal reached with zero receivers connected

    received: list[object] = []
    runnable.signals.failed.connect(lambda event: received.append(event))
    runnable.replay_pending_terminal()

    assert len(received) == 1
    assert isinstance(received[0], TaskFailed)
    assert "boom before any subscriber connected" in str(received[0].message)

    # Replay is one-shot: a second call delivers nothing.
    runnable.replay_pending_terminal()
    assert len(received) == 1


def test_replay_pending_terminal_noop_when_task_still_running() -> None:
    """No terminal yet → replay is a no-op and delivers nothing."""
    from photo_archiver.workers.qt_executor import QtWorkerRunnable

    class _IdleTask(WorkerTask[object]):
        def __init__(self) -> None:
            super().__init__("idle")

        def execute(self) -> object:  # pragma: no cover - never invoked here
            raise AssertionError("not executed in this test")

    runnable = QtWorkerRunnable(_IdleTask())
    received: list[object] = []
    runnable.signals.completed.connect(lambda event: received.append(event))
    runnable.replay_pending_terminal()

    assert received == []
