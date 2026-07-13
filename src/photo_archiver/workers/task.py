"""Worker task primitives.

The worker layer coordinates long-running application use cases and emits
progress-friendly events for presentation adapters. This module intentionally
contains no domain decisions and does not depend on PySide6, so it can be
tested synchronously and later wrapped by Qt-specific executors in
``qt_executor.py`` (per DEP-040 the Qt threading boundary is authorized for
the workers layer).
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from loguru import logger

from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskEvent,
    TaskEventHandler,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)

ResultT = TypeVar("ResultT")


class WorkerTaskCancelled(Exception):
    """Raised when a worker task is cancelled cooperatively."""


class WorkerTask(ABC, Generic[ResultT]):
    """Base class for executable worker tasks."""

    def __init__(self, name: str) -> None:
        """Initialize the task with a stable display/logging name."""
        self.name = name
        self._event_handlers: list[TaskEventHandler] = []
        self._cancel_requested = False
        self._cancel_reason = ""

    def subscribe(self, handler: TaskEventHandler) -> None:
        """Subscribe to task lifecycle events."""
        self._event_handlers.append(handler)

    def run(self) -> ResultT:
        """Execute the task and emit started/completed/failed events."""
        self._emit(TaskStarted(self.name))
        try:
            self.raise_if_cancelled()
            result = self.execute()
            self.raise_if_cancelled()
        except WorkerTaskCancelled as exc:
            logger.info("Worker task {} cancelled: {}", self.name, exc)
            self._emit(TaskCancelled(self.name, str(exc)))
            raise
        except Exception as exc:
            logger.exception("Worker task {} failed", self.name)
            self._emit(TaskFailed(self.name, exc))
            raise

        self._emit(TaskCompleted(self.name, result))
        return result

    def cancel(self, reason: str = "") -> None:
        """Request cooperative cancellation for the task."""
        self._cancel_requested = True
        self._cancel_reason = reason

    @property
    def is_cancel_requested(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancel_requested

    def raise_if_cancelled(self) -> None:
        """Raise if cooperative cancellation has been requested."""
        if self._cancel_requested:
            reason = self._cancel_reason or f"{self.name} was cancelled"
            raise WorkerTaskCancelled(reason)

    def report_progress(
        self,
        message: str = "",
        *,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Emit a progress event from a concrete task implementation."""
        self._emit(TaskProgress(self.name, message=message, current=current, total=total))

    def report(self, current: int, total: int, message: str = "") -> None:
        """ProgressReporter protocol adapter for use-case injection.

        Translates the ``ProgressReporter.report`` signature into the worker
        task's native ``report_progress`` event so services can stream progress
        through a bound task without depending on the worker layer.
        """
        self.report_progress(message=message, current=current, total=total)

    @abstractmethod
    def execute(self) -> ResultT:
        """Run the concrete task implementation."""

    def _emit(self, event: TaskEvent) -> None:
        for handler in self._event_handlers:
            handler(event)