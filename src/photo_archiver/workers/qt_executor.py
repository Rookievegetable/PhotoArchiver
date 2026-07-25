"""Qt executor for running worker tasks outside the UI thread."""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from loguru import logger

from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskEvent,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)
from photo_archiver.workers.task import WorkerTask, WorkerTaskCancelled


class QtWorkerSignals(QObject):
    """Qt signals emitted from worker task events."""

    event = Signal(object)  # type: ignore[assignment]
    started = Signal(object)  # type: ignore[assignment]  # SignalInstance vs Callable variance
    progress = Signal(object)  # type: ignore[assignment]
    completed = Signal(object)  # type: ignore[assignment]
    failed = Signal(object)  # type: ignore[assignment]
    cancelled = Signal(object)


class QtWorkerRunnable(QRunnable):
    """QRunnable adapter that executes a WorkerTask in a Qt thread pool."""

    def __init__(self, task: WorkerTask[object]) -> None:
        """Initialize the runnable with a worker task."""
        super().__init__()
        self.task = task
        self.signals = QtWorkerSignals()
        self.task.subscribe(self._emit_task_event)

    def cancel(self, reason: str = "") -> None:
        """Request cooperative cancellation for the wrapped task."""
        self.task.cancel(reason)

    @Slot()
    def run(self) -> None:
        """Run the task in a background Qt thread.

        WorkerTask.run() already emits TaskFailed and re-raises on exception,
        so this wrapper only catches the re-raised exception to keep Qt thread
        exit clean. A debug log line is left here so thread-layer crashes are
        observable in logs even though the task layer has already reported.
        """
        try:
            self.task.run()
        except WorkerTaskCancelled:
            return
        except Exception as exc:  # noqa: BLE001 - task layer already emitted TaskFailed
            logger.debug(
                "QtWorkerRunnable task '{}' ended with exception (already emitted as TaskFailed): {}",
                self.task.name,
                exc,
            )
            return

    def _emit_task_event(self, event: TaskEvent) -> None:
        self.signals.event.emit(event)
        if isinstance(event, TaskStarted):
            self.signals.started.emit(event)
        elif isinstance(event, TaskProgress):
            self.signals.progress.emit(event)
        elif isinstance(event, TaskCompleted):
            self.signals.completed.emit(event)
        elif isinstance(event, TaskFailed):
            self.signals.failed.emit(event)
        elif isinstance(event, TaskCancelled):
            self.signals.cancelled.emit(event)


class QtWorkerExecutor:
    """Submit worker tasks to a Qt thread pool."""

    def __init__(
        self,
        thread_pool: QThreadPool | None = None,
        max_workers: int | None = None,
    ) -> None:
        """Initialize the executor with the provided or global thread pool.

        Args:
            thread_pool: Optional QThreadPool; defaults to the global instance.
            max_workers: Optional concurrency cap forwarded to the pool's
                ``setMaxThreadCount``. When ``None`` the pool keeps its default.
        """
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        if max_workers is not None:
            self._thread_pool.setMaxThreadCount(max_workers)

    def submit(self, task: WorkerTask[object]) -> QtWorkerRunnable:
        """Submit a task for background execution and return its runnable handle."""
        runnable = QtWorkerRunnable(task)
        self._thread_pool.start(runnable)
        return runnable