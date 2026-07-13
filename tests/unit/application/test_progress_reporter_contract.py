"""Tests for the ProgressReporter port and WorkerTask adapter conformance."""

from photo_archiver.application.ports import ProgressReporter
from photo_archiver.workers import WorkerTask


class RecordingReporter:
    """Minimal ProgressReporter implementation that records calls for assertions."""

    def __init__(self) -> None:
        """Initialize the call log."""
        self.calls: list[tuple[int, int, str]] = []

    def report(self, current: int, total: int, message: str = "") -> None:
        """Record a progress report."""
        self.calls.append((current, total, message))


class _Task(WorkerTask[str]):
    """Trivial task used to verify report adapter."""

    def __init__(self) -> None:
        super().__init__("test")

    def execute(self) -> str:
        return "ok"


def test_progress_reporter_is_protocol() -> None:
    """ProgressReporter should be a runtime-checkable Protocol."""
    reporter = RecordingReporter()
    assert isinstance(reporter, ProgressReporter)


def test_worker_task_report_satisfies_protocol() -> None:
    """WorkerTask.report adapter should conform to ProgressReporter."""
    task = _Task()
    assert isinstance(task, ProgressReporter)


def test_worker_task_report_translates_to_progress_event() -> None:
    """WorkerTask.report should emit a TaskProgress event with current/total."""
    task = _Task()
    events: list = []
    task.subscribe(events.append)
    task.report(5, 10, "halfway")
    progress = events[-1]
    assert progress.current == 5
    assert progress.total == 10
    assert "halfway" in progress.message
