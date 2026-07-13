"""Worker task event models."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeAlias


@dataclass(frozen=True, slots=True)
class TaskStarted:
    """Event emitted when a worker task starts."""

    task_name: str


@dataclass(frozen=True, slots=True)
class TaskProgress:
    """Event emitted when a worker task reports progress."""

    task_name: str
    message: str = ""
    current: int | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class TaskCompleted:
    """Event emitted when a worker task completes successfully."""

    task_name: str
    result: Any = None


@dataclass(frozen=True, slots=True)
class TaskFailed:
    """Event emitted when a worker task fails."""

    task_name: str
    error: Exception

    @property
    def message(self) -> str:
        """Return a user-readable failure message."""
        return str(self.error)


@dataclass(frozen=True, slots=True)
class TaskCancelled:
    """Event emitted when a worker task is cancelled."""

    task_name: str
    reason: str = ""


TaskEvent: TypeAlias = TaskStarted | TaskProgress | TaskCompleted | TaskFailed | TaskCancelled
TaskEventHandler: TypeAlias = Callable[[TaskEvent], None]