"""Background worker task primitives and application task wrappers."""

from photo_archiver.workers.application_tasks import ImportPeopleTask, ScanAndRegisterPhotosTask
from photo_archiver.workers.events import (
    TaskCancelled,
    TaskCompleted,
    TaskEvent,
    TaskEventHandler,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)
from photo_archiver.workers.qt_executor import QtWorkerExecutor, QtWorkerRunnable, QtWorkerSignals
from photo_archiver.workers.task import WorkerTask, WorkerTaskCancelled

__all__ = [
    "ImportPeopleTask",
    "QtWorkerExecutor",
    "QtWorkerRunnable",
    "QtWorkerSignals",
    "TaskCancelled",
    "ScanAndRegisterPhotosTask",
    "TaskCompleted",
    "TaskEvent",
    "TaskEventHandler",
    "TaskFailed",
    "TaskProgress",
    "TaskStarted",
    "WorkerTask",
    "WorkerTaskCancelled",
]
